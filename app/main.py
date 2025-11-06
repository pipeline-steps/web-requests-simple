import sys
import os
import json
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore, Lock, Thread, Event
from steputil import StepArgs, StepArgsBuilder

# Import auth module from same directory
from auth import get_access_token


class ProgressTracker:
    """Thread-safe progress tracker for monitoring request processing."""

    def __init__(self, total_requests):
        self.total_requests = total_requests
        self.completed = 0
        self.errors = 0
        self.start_time = time.time()
        self.lock = Lock()

    def increment(self, is_error=False):
        """Increment completed count and optionally error count."""
        with self.lock:
            self.completed += 1
            if is_error:
                self.errors += 1

    def get_stats(self):
        """Get current statistics."""
        with self.lock:
            elapsed = time.time() - self.start_time
            requests_per_minute = (self.completed / elapsed * 60) if elapsed > 0 else 0
            return {
                'completed': self.completed,
                'errors': self.errors,
                'total': self.total_requests,
                'elapsed': elapsed,
                'requests_per_minute': requests_per_minute
            }


class RateLimiter:
    """Rate limiter that controls the maximum number of requests per minute."""

    def __init__(self, max_requests_per_minute):
        self.max_requests = max_requests_per_minute
        if max_requests_per_minute > 0:
            self.min_interval = 60.0 / max_requests_per_minute
        else:
            self.min_interval = 0
        self.last_request_time = 0
        self.lock = Lock()

    def acquire(self):
        """Wait if necessary to respect the rate limit."""
        if self.max_requests <= 0:
            return  # No rate limiting

        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time

            if time_since_last < self.min_interval:
                sleep_time = self.min_interval - time_since_last
                time.sleep(sleep_time)

            self.last_request_time = time.time()


def progress_reporter(tracker, stop_event, interval=10):
    """Background thread that prints progress every interval seconds."""
    while not stop_event.is_set():
        if stop_event.wait(interval):
            break
        stats = tracker.get_stats()
        print(f"Progress: {stats['completed']}/{stats['total']} requests "
              f"({stats['errors']} errors) | "
              f"Elapsed: {stats['elapsed']:.1f}s | "
              f"Rate: {stats['requests_per_minute']:.1f} req/min",
              file=sys.stderr)


def process_request(idx, record, headers, rate_limiter, progress_tracker):
    """Process a single request and return the result."""
    # Extract request fields
    method = record.get('method', 'GET').upper()
    url = record.get('url')
    body = record.get('body')

    if not url:
        progress_tracker.increment(is_error=True)
        return None

    # Prepare the result entry
    result = {
        'request': {
            'method': method,
            'url': url,
            'body': body
        },
        'response': {}
    }

    # Apply rate limiting before making the request
    rate_limiter.acquire()

    # Issue the request
    try:
        if method in ['GET', 'DELETE']:
            response = requests.request(method, url, headers=headers)
        elif method in ['POST', 'PUT', 'PATCH']:
            if body:
                # Assume body is already a dict/object
                response = requests.request(method, url, json=body, headers=headers)
            else:
                response = requests.request(method, url, headers=headers)
        else:
            response = requests.request(method, url, headers=headers)

        # Capture response
        result['response']['status'] = response.status_code

        # Try to parse response as JSON, otherwise store as text
        try:
            result['response']['body'] = response.json()
        except:
            result['response']['body'] = response.text

        result['success'] = 200 <= response.status_code < 300
        progress_tracker.increment(is_error=not result['success'])

    except Exception as e:
        result['response']['status'] = None
        result['response']['message'] = str(e)
        result['success'] = False
        progress_tracker.increment(is_error=True)

    return result


def main(step: StepArgs):
    # Prepare headers - start with custom headers if provided
    headers = {}
    if step.config.headers:
        headers.update(step.config.headers)
        print(f"Using custom headers: {list(step.config.headers.keys())}")

    # Optionally add Google authentication
    if step.config.useGoogleToken:
        print("Getting credentials from Application Default Credentials (ADC)")
        scopes = step.config.scopes if step.config.scopes else []
        token = get_access_token(scopes)
        headers['Authorization'] = f'Bearer {token}'
        print(f"Added Bearer token to request headers")

    # Read input jsonl with request information
    records = step.input.readJsons()
    print(f"Processing {len(records)} requests...")

    # Get concurrency and rate limit settings
    concurrency = step.config.concurrency if step.config.concurrency else 1
    rate_limit = step.config.rateLimit if step.config.rateLimit else 0

    print(f"Using concurrency: {concurrency}")
    if rate_limit > 0:
        print(f"Rate limit: {rate_limit} requests/minute")
    else:
        print("Rate limit: disabled")

    # Initialize rate limiter and progress tracker
    rate_limiter = RateLimiter(rate_limit)
    progress_tracker = ProgressTracker(len(records))

    # Start progress reporter thread
    stop_event = Event()
    reporter_thread = Thread(target=progress_reporter, args=(progress_tracker, stop_event), daemon=True)
    reporter_thread.start()

    results = []

    # Process requests with threading
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all requests
        future_to_idx = {
            executor.submit(process_request, idx, record, headers, rate_limiter, progress_tracker): idx
            for idx, record in enumerate(records)
        }

        # Collect results as they complete
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                if result:
                    results.append((idx, result))
            except Exception as e:
                progress_tracker.increment(is_error=True)
                print(f"Unexpected error processing request {idx + 1}: {e}", file=sys.stderr)

    # Stop progress reporter
    stop_event.set()
    reporter_thread.join()

    # Sort results by original index to maintain order
    results.sort(key=lambda x: x[0])
    results = [r[1] for r in results]

    # Remove success flag before writing (internal use only)
    for result in results:
        result.pop('success', None)

    # Write output
    step.output.writeJsons(results)

    # Print final statistics
    final_stats = progress_tracker.get_stats()
    print(f"Done. Processed {final_stats['completed']}/{final_stats['total']} requests: "
          f"{final_stats['completed'] - final_stats['errors']} successful, {final_stats['errors']} errors. "
          f"Total time: {final_stats['elapsed']:.1f}s | "
          f"Average rate: {final_stats['requests_per_minute']:.1f} req/min")


def validate_config(config):
    """Validation function that checks config rules."""
    # Check that scopes is only used when useGoogleToken is true
    if config.scopes and not config.useGoogleToken:
        print("Parameter `scopes` can only be used when `useGoogleToken` is true", file=sys.stderr)
        return False

    # Check that Authorization header doesn't conflict with useGoogleToken
    if config.useGoogleToken and config.headers:
        if 'Authorization' in config.headers:
            print("Cannot use `useGoogleToken` when custom `Authorization` header is provided in `headers`", file=sys.stderr)
            return False

    return True


if __name__ == "__main__":
    main(StepArgsBuilder()
         .input()
         .output(optional=True)
         .config("useGoogleToken", optional=True)
         .config("scopes", optional=True)
         .config("headers", optional=True)
         .config("concurrency", optional=True)
         .config("rateLimit", optional=True)
         .validate(validate_config)
         .build()
         )

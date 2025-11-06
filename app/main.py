import sys
import os
import json
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore, Lock
from steputil import StepArgs, StepArgsBuilder

# Import auth module from same directory
from auth import get_access_token


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


def process_request(idx, record, headers, rate_limiter):
    """Process a single request and return the result."""
    # Extract request fields
    method = record.get('method', 'GET').upper()
    url = record.get('url')
    body = record.get('body')

    if not url:
        print(f"Warning: Request {idx + 1} missing URL, skipping", file=sys.stderr)
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
        print(f"Issuing {method} request to {url}...")

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

        if not result['success']:
            print(f"Request {idx + 1} returned status {response.status_code}", file=sys.stderr)

    except Exception as e:
        result['response']['status'] = None
        result['response']['message'] = str(e)
        result['success'] = False
        print(f"Error processing request {idx + 1}: {e}", file=sys.stderr)

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

    # Initialize rate limiter
    rate_limiter = RateLimiter(rate_limit)

    results = []
    success_count = 0
    error_count = 0

    # Process requests with threading
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all requests
        future_to_idx = {
            executor.submit(process_request, idx, record, headers, rate_limiter): idx
            for idx, record in enumerate(records)
        }

        # Collect results as they complete
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                if result:
                    results.append((idx, result))
                    if result.get('success', False):
                        success_count += 1
                    else:
                        error_count += 1
            except Exception as e:
                error_count += 1
                print(f"Unexpected error processing request {idx + 1}: {e}", file=sys.stderr)

    # Sort results by original index to maintain order
    results.sort(key=lambda x: x[0])
    results = [r[1] for r in results]

    # Remove success flag before writing (internal use only)
    for result in results:
        result.pop('success', None)

    # Write output
    step.output.writeJsons(results)

    print(f"Done. Processed {len(results)} requests: {success_count} successful, {error_count} errors.")


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

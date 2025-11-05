import sys
import os
import json
import requests
from steputil import StepArgs, StepArgsBuilder
from .auth import get_access_token


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

    results = []
    success_count = 0
    error_count = 0

    for idx, record in enumerate(records):
        # Extract request fields
        method = record.get('method', 'GET').upper()
        url = record.get('url')
        body = record.get('body')

        if not url:
            print(f"Warning: Request {idx + 1} missing URL, skipping", file=sys.stderr)
            continue

        # Prepare the result entry
        result = {
            'request': {
                'method': method,
                'url': url,
                'body': body
            },
            'response': {}
        }

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

            if 200 <= response.status_code < 300:
                success_count += 1
            else:
                error_count += 1
                print(f"Request {idx + 1} returned status {response.status_code}", file=sys.stderr)

        except Exception as e:
            error_count += 1
            result['response']['status'] = None
            result['response']['message'] = str(e)
            print(f"Error processing request {idx + 1}: {e}", file=sys.stderr)

        results.append(result)

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
         .validate(validate_config)
         .build()
         )

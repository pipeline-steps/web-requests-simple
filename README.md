# web-requests-simple

Issuing REST requests to an API (simple version)

## Overview

This pipeline step reads a JSONL input file containing request information and issues HTTP requests for each entry. The results are written to an output JSONL file with both the original request and the response data.

## Docker Image

This application is available as a Docker image on Docker Hub: `pipelining/web-requests-simple`

### Usage

```bash
docker run -v /path/to/input.jsonl:/input.jsonl \
           -v /path/to/output:/output \
           pipelining/web-requests-simple:latest \
           --input /input.jsonl \
           --output /output/results.jsonl
```

To see this documentation, run without arguments:
```bash
docker run pipelining/web-requests-simple:latest
```

## Input Format

The input JSONL file should contain one JSON object per line with the following fields:

| Field  | Required | Description                                          |
|--------|----------|------------------------------------------------------|
| method | No       | HTTP method (GET, POST, PUT, PATCH, DELETE). Default: GET |
| url    | Yes      | The URL endpoint to send the request to              |
| body   | No       | Request body (for POST, PUT, PATCH requests)         |

### Input Example

```jsonl
{"method": "GET", "url": "https://api.example.com/users/1"}
{"method": "POST", "url": "https://api.example.com/users", "body": {"name": "John", "email": "john@example.com"}}
{"method": "PUT", "url": "https://api.example.com/users/1", "body": {"name": "John Doe"}}
{"method": "DELETE", "url": "https://api.example.com/users/1"}
```

## Output Format

The output JSONL file contains one JSON object per line with the following structure:

### Successful Response

```json
{
  "timestamp": "2025-01-12 10:30:45",
  "request": {
    "method": "POST",
    "url": "https://api.example.com/users",
    "body": {"name": "John", "email": "john@example.com"}
  },
  "result": {"id": 123, "name": "John", "email": "john@example.com"},
  "meta": {
    "durationMillis": 234,
    "status": 201,
    "message": ""
  }
}
```

### Error Response (HTTP Error)

```json
{
  "timestamp": "2025-01-12 10:30:45",
  "request": {
    "method": "GET",
    "url": "https://api.example.com/users/999"
  },
  "meta": {
    "durationMillis": 234,
    "status": 404,
    "message": "{\"error\": \"User not found\"}"
  }
}
```

### Error Response (Connection Error)

```json
{
  "timestamp": "2025-01-12 10:30:45",
  "request": {
    "method": "GET",
    "url": "https://api.example.com/users/999"
  },
  "meta": {
    "durationMillis": 156,
    "status": null,
    "message": "Connection timeout"
  }
}
```

### Output Fields

- `timestamp`: UTC timestamp when the request was issued, formatted according to timestampFormat config parameter (default: "2025-01-12 10:30:45")
- `request`: Copy of the original request information
- `result`: Response body (parsed as JSON if possible, otherwise as text). **Only present on successful requests (HTTP 2xx status codes).**
- `meta.durationMillis`: Time elapsed in milliseconds from request start to response received
- `meta.status`: HTTP status code (or null if connection/network error occurred)
- `meta.message`: Error message or response body (empty string on success, response body for HTTP errors 4xx/5xx, error description for connection errors)

**Notes**:
- The `result` field is omitted on errors (not null, but missing from the object)
- Success is determined by HTTP status code: 200-299 range = success, anything else = error
- For HTTP errors (4xx, 5xx), the response body is stored in `meta.message` instead of `result`
- The `timestamp` field is stored as a Python datetime object, which pandas will convert to BigQuery TIMESTAMP type
- Any `@type` fields in JSON responses are automatically renamed to `type` for BigQuery compatibility

## Configuration Parameters

| Name            | Required | Description                                                              |
|-----------------|----------|--------------------------------------------------------------------------|
| useGoogleToken  |          | If true, uses Google Application Default Credentials to add Bearer token |
| scopes          |          | List of OAuth scopes to request (only valid when useGoogleToken is true) |
| headers         |          | Dictionary of custom HTTP headers to include in all requests            |
| concurrency     |          | Number of concurrent threads for parallel request processing (default: 1) |
| rateLimit       |          | Maximum number of requests per minute (default: 0 = no limit)           |
| timestampFormat |          | Python datetime format string for timestamp field (default: "%Y-%m-%d %H:%M:%S") |

**Notes:**
  * useGoogleToken: When enabled, the pipeline will use ADC to obtain a Google OAuth token and add it as `Authorization: Bearer <token>` header to all requests
  * useGoogleToken: Requires GOOGLE_APPLICATION_CREDENTIALS environment variable to be set or gcloud to be configured
  * scopes: Optional list of OAuth scopes (e.g., `["https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/webmasters"]`). If not specified, default scopes will be used. Can only be used when useGoogleToken is true.
  * headers: Optional dictionary of HTTP headers (e.g., `{"User-Agent": "MyApp/1.0", "Accept-Language": "en-US"}`). These headers will be merged with any authentication headers and applied to all requests.
  * concurrency: Controls how many requests can be processed simultaneously using threads. A value of 1 (default) means sequential processing. Higher values enable parallel processing. For example, concurrency of 10 allows up to 10 requests to be processed at the same time.
  * rateLimit: Controls the maximum number of requests per minute. A value of 0 (default) means no rate limiting. For example, a rateLimit of 60 allows at most 60 requests per minute (1 per second). Rate limiting works together with concurrency to prevent overwhelming APIs.
  * timestampFormat: Format string for the timestamp field in the output. Uses Python's strftime format (e.g., "%Y-%m-%d %H:%M:%S" produces "2021-07-07 23:10:47"). Defaults to "%Y-%m-%d %H:%M:%S".

### Configuration Example

```json
{
  "useGoogleToken": true,
  "scopes": ["https://www.googleapis.com/auth/cloud-platform"],
  "headers": {
    "User-Agent": "MyApp/1.0"
  },
  "concurrency": 10,
  "rateLimit": 60
}
```

This configuration will:
- Use Google authentication with cloud platform scope
- Add a custom User-Agent header
- Process up to 10 requests in parallel
- Limit to maximum 60 requests per minute (1 per second)

With Google authentication (using ADC):
```bash
docker run -v /path/to/input.jsonl:/input.jsonl \
           -v /path/to/output:/output \
           -v /path/to/config.json:/config.json \
           -v /path/to/credentials.json:/credentials.json \
           -e GOOGLE_APPLICATION_CREDENTIALS=/credentials.json \
           pipelining/web-requests-simple:latest \
           --input /input.jsonl \
           --config /config.json \
           --output /output/results.jsonl
```

## Error Handling

- Requests that fail will still be included in the output with a `message` field in the response
- The step will continue processing remaining requests even if some fail
- Summary statistics are printed at the end showing successful vs. failed requests

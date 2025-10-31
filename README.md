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

```json
{
  "request": {
    "method": "POST",
    "url": "https://api.example.com/users",
    "body": {"name": "John", "email": "john@example.com"}
  },
  "response": {
    "status": 201,
    "body": {"id": 123, "name": "John", "email": "john@example.com"}
  }
}
```

### Response Fields

- `request`: Copy of the original request information
- `response.status`: HTTP status code (or null if request failed)
- `response.body`: Response body (parsed as JSON if possible, otherwise as text)
- `response.message`: Error message (only present if request failed)

## Configuration Parameters

| Name            | Required | Description                                                              |
|-----------------|----------|--------------------------------------------------------------------------|
| useGoogleToken  |          | If true, uses Google Application Default Credentials to add Bearer token |
| scopes          |          | List of OAuth scopes to request (only valid when useGoogleToken is true) |
| headers         |          | Dictionary of custom HTTP headers to include in all requests            |

**Notes:**
  * useGoogleToken: When enabled, the pipeline will use ADC to obtain a Google OAuth token and add it as `Authorization: Bearer <token>` header to all requests
  * useGoogleToken: Requires GOOGLE_APPLICATION_CREDENTIALS environment variable to be set or gcloud to be configured
  * scopes: Optional list of OAuth scopes (e.g., `["https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/webmasters"]`). If not specified, default scopes will be used. Can only be used when useGoogleToken is true.
  * headers: Optional dictionary of HTTP headers (e.g., `{"User-Agent": "MyApp/1.0", "Accept-Language": "en-US"}`). These headers will be merged with any authentication headers and applied to all requests.

### Configuration Example

```json
{
  "useGoogleToken": true,
  "scopes": ["https://www.googleapis.com/auth/cloud-platform"],
  "headers": {
    "User-Agent": "MyApp/1.0"
  }
}
```

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

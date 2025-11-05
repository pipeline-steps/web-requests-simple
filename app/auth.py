import os
import sys
from google.auth import default
from google.auth.transport.requests import Request
from google.auth import impersonated_credentials


def get_access_token(scopes, lifetime=3600):
    """
    Authenticates using Application Default Credentials (ADC).
    In a Kubernetes environment with Workload Identity, this will automatically
    use the service account assigned to the pod.

    If GOOGLE_IMPERSONATE_SERVICE_ACCOUNT environment variable is set,
    impersonates that service account to generate the access token.

    Args:
        scopes: List of OAuth2 scopes required for authentication
        lifetime: Token lifetime in seconds (default: 3600 = 1 hour)

    Returns:
        Access token string

    Exits:
        Exits with code 1 if authentication fails
    """
    if scopes:
        print(f"Using scopes: {scopes}")

    try:
        # Get the target service account to impersonate (if set)
        target_service_account = os.getenv('GOOGLE_IMPERSONATE_SERVICE_ACCOUNT')

        if target_service_account:
            # First, get source credentials (from ADC)
            source_credentials, project_id = default()

            # Create impersonated credentials
            print(f"Impersonating service account: {target_service_account}", file=sys.stderr)
            credentials = impersonated_credentials.Credentials(
                source_credentials=source_credentials,
                target_principal=target_service_account,
                target_scopes=scopes,
                lifetime=lifetime
            )
        else:
            # Use default credentials without impersonation
            credentials, project_id = default(scopes=scopes)

        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        print(f"Error during authentication: {e}", file=sys.stderr)
        print("Failed to get access token. Exiting.", file=sys.stderr)
        sys.exit(1)

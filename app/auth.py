import os
import sys
from threading import Lock
from google.auth import default
from google.auth.transport.requests import Request
from google.auth import impersonated_credentials


class TokenManager:
    """Thread-safe token manager that handles token refresh."""

    def __init__(self, scopes, lifetime=3600):
        """
        Initialize the token manager.

        Args:
            scopes: List of OAuth2 scopes required for authentication
            lifetime: Token lifetime in seconds (default: 3600 = 1 hour)
        """
        self.scopes = scopes
        self.lifetime = lifetime
        self.credentials = None
        self.lock = Lock()
        self._initialize_credentials()

    def _initialize_credentials(self):
        """Initialize credentials using ADC."""
        if self.scopes:
            print(f"Using scopes: {self.scopes}")

        try:
            # Get the target service account to impersonate (if set)
            target_service_account = os.getenv('GOOGLE_IMPERSONATE_SERVICE_ACCOUNT')

            if target_service_account:
                # First, get source credentials (from ADC)
                source_credentials, project_id = default()

                # Create impersonated credentials
                print(f"Impersonating service account: {target_service_account}", file=sys.stderr)
                self.credentials = impersonated_credentials.Credentials(
                    source_credentials=source_credentials,
                    target_principal=target_service_account,
                    target_scopes=self.scopes,
                    lifetime=self.lifetime
                )
            else:
                # Use default credentials without impersonation
                self.credentials, project_id = default(scopes=self.scopes)

            self.credentials.refresh(Request())
        except Exception as e:
            print(f"Error during authentication: {e}", file=sys.stderr)
            print("Failed to get access token. Exiting.", file=sys.stderr)
            sys.exit(1)

    def get_token(self):
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            Access token string
        """
        with self.lock:
            # Check if token needs refresh
            if not self.credentials.valid:
                print("Token expired, refreshing...", file=sys.stderr)
                try:
                    self.credentials.refresh(Request())
                    print("Token refreshed successfully", file=sys.stderr)
                except Exception as e:
                    print(f"Error refreshing token: {e}", file=sys.stderr)
                    print("Failed to refresh access token. Exiting.", file=sys.stderr)
                    sys.exit(1)

            return self.credentials.token

    def force_refresh(self):
        """
        Force refresh the token (useful when a 401 error is received).

        Returns:
            New access token string
        """
        with self.lock:
            print("Forcing token refresh...", file=sys.stderr)
            try:
                self.credentials.refresh(Request())
                print("Token refreshed successfully", file=sys.stderr)
                return self.credentials.token
            except Exception as e:
                print(f"Error refreshing token: {e}", file=sys.stderr)
                print("Failed to refresh access token. Exiting.", file=sys.stderr)
                sys.exit(1)


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

"""
Apollo.io Integration Service

Provides candidate sourcing through Apollo.io's People Search API.
Supports searching, enrichment, and email finding with rate limiting
and pagination for bulk operations.
"""
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Apollo API base URL
APOLLO_API_BASE = "https://api.apollo.io/v1"

# Rate limiting configuration
RATE_LIMIT_REQUESTS_PER_MINUTE = 50
RATE_LIMIT_WINDOW_SECONDS = 60


class ApolloRateLimitError(Exception):
    """Raised when Apollo rate limit is exceeded."""

    def __init__(self, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s" if retry_after else "Rate limit exceeded")


class ApolloAPIError(Exception):
    """Raised when Apollo API returns an error."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Apollo API error ({status_code}): {message}")


class ApolloService:
    """
    Service for integrating with Apollo.io's API.

    Provides methods for:
    - Searching people by criteria (title, company, industry, etc.)
    - Enriching person profiles from LinkedIn URLs
    - Finding verified email addresses

    Includes stub mode for development when APOLLO_API_KEY is not set.
    """

    def __init__(self):
        self.api_key = settings.apollo_api_key
        self.stub_mode = not bool(self.api_key)
        self._request_timestamps: List[float] = []

        if self.stub_mode:
            logger.warning("Apollo service running in STUB mode - no API key configured")
        else:
            logger.info("Apollo service initialized with API key")

    def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting."""
        current_time = time.time()

        # Remove timestamps older than the window
        self._request_timestamps = [
            ts for ts in self._request_timestamps
            if current_time - ts < RATE_LIMIT_WINDOW_SECONDS
        ]

        if len(self._request_timestamps) >= RATE_LIMIT_REQUESTS_PER_MINUTE:
            oldest_timestamp = min(self._request_timestamps)
            retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (current_time - oldest_timestamp)) + 1
            raise ApolloRateLimitError(retry_after=retry_after)

        self._request_timestamps.append(current_time)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Make an authenticated request to Apollo API."""
        if self.stub_mode:
            raise ValueError("Cannot make API request in stub mode")

        self._check_rate_limit()

        url = f"{APOLLO_API_BASE}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.api_key,
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params if method == "GET" else None,
                    json=json_data if method == "POST" else None,
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise ApolloRateLimitError(
                        retry_after=int(retry_after) if retry_after else 60
                    )

                if response.status_code >= 400:
                    error_message = response.text
                    try:
                        error_data = response.json()
                        error_message = error_data.get("error", error_message)
                    except Exception:
                        pass
                    raise ApolloAPIError(response.status_code, error_message)

                return response.json()

        except httpx.TimeoutException:
            raise ApolloAPIError(408, "Request timed out")
        except httpx.RequestError as e:
            raise ApolloAPIError(500, f"Request failed: {str(e)}")

    def _map_person_to_candidate(self, person: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map Apollo person response to our Candidate model fields.

        Apollo fields -> Candidate fields:
        - first_name -> first_name
        - last_name -> last_name
        - name -> full_name
        - title -> title
        - organization.name -> company
        - organization.estimated_num_employees -> company_employee_count
        - linkedin_url -> linkedin_url
        - email -> email
        - city, state, country -> region
        """
        organization = person.get("organization") or {}

        # Build region string from location parts
        location_parts = []
        if person.get("city"):
            location_parts.append(person["city"])
        if person.get("state"):
            location_parts.append(person["state"])
        if person.get("country"):
            location_parts.append(person["country"])
        region = ", ".join(location_parts) if location_parts else None

        # Build full name if not provided
        first_name = person.get("first_name")
        last_name = person.get("last_name")
        full_name = person.get("name")
        if not full_name and (first_name or last_name):
            full_name = f"{first_name or ''} {last_name or ''}".strip()

        return {
            "apollo_id": person.get("id"),
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name or "Unknown",
            "title": person.get("title"),
            "company": organization.get("name"),
            "company_employee_count": organization.get("estimated_num_employees"),
            "linkedin_url": person.get("linkedin_url"),
            "email": person.get("email"),
            "email_verified": person.get("email_status") == "verified",
            "region": region,
            # Additional Apollo fields for reference
            "apollo_data": {
                "organization_id": organization.get("id"),
                "industry": organization.get("industry"),
                "seniority": person.get("seniority"),
                "departments": person.get("departments", []),
                "email_status": person.get("email_status"),
                "phone_numbers": person.get("phone_numbers", []),
            }
        }

    def _get_mock_people(self, criteria: Dict[str, Any], page: int = 1) -> Dict[str, Any]:
        """Return mock data for stub mode."""
        mock_people = [
            {
                "id": "mock-person-001",
                "first_name": "Jane",
                "last_name": "Smith",
                "name": "Jane Smith",
                "title": "VP of Benefits",
                "organization": {
                    "id": "mock-org-001",
                    "name": "Acme Corporation",
                    "estimated_num_employees": 15000,
                    "industry": "Financial Services",
                },
                "linkedin_url": "https://www.linkedin.com/in/janesmith",
                "email": "jane.smith@acme.com",
                "email_status": "verified",
                "city": "New York",
                "state": "NY",
                "country": "United States",
                "seniority": "vp",
                "departments": ["Human Resources"],
            },
            {
                "id": "mock-person-002",
                "first_name": "John",
                "last_name": "Doe",
                "name": "John Doe",
                "title": "Director of 401(k) Administration",
                "organization": {
                    "id": "mock-org-002",
                    "name": "Tech Innovations Inc",
                    "estimated_num_employees": 25000,
                    "industry": "Technology",
                },
                "linkedin_url": "https://www.linkedin.com/in/johndoe",
                "email": "john.doe@techinnovations.com",
                "email_status": "verified",
                "city": "San Francisco",
                "state": "CA",
                "country": "United States",
                "seniority": "director",
                "departments": ["Human Resources", "Finance"],
            },
            {
                "id": "mock-person-003",
                "first_name": "Sarah",
                "last_name": "Johnson",
                "name": "Sarah Johnson",
                "title": "Benefits Manager",
                "organization": {
                    "id": "mock-org-003",
                    "name": "Global Enterprises",
                    "estimated_num_employees": 50000,
                    "industry": "Manufacturing",
                },
                "linkedin_url": "https://www.linkedin.com/in/sarahjohnson",
                "email": "sarah.johnson@globalent.com",
                "email_status": "guessed",
                "city": "Chicago",
                "state": "IL",
                "country": "United States",
                "seniority": "manager",
                "departments": ["Human Resources"],
            },
        ]

        return {
            "people": mock_people,
            "pagination": {
                "page": page,
                "per_page": 25,
                "total_entries": len(mock_people),
                "total_pages": 1,
            }
        }

    def search_people(
        self,
        criteria: Dict[str, Any],
        page: int = 1,
        per_page: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Search Apollo for people matching the specified criteria.

        Args:
            criteria: Search criteria including:
                - titles: List of job titles to match
                - company_sizes: List of company size ranges (e.g., ["1001-5000", "5001-10000"])
                - industries: List of industries
                - locations: List of locations (city, state, country)
                - keywords: List of keywords for broader matching
                - seniorities: List of seniority levels (e.g., ["director", "vp", "c_suite"])
            page: Page number for pagination (1-indexed)
            per_page: Results per page (max 100)

        Returns:
            List of candidate dictionaries mapped to our Candidate model fields.

        Raises:
            ApolloRateLimitError: If rate limit is exceeded
            ApolloAPIError: If Apollo API returns an error
        """
        if self.stub_mode:
            logger.info(f"[STUB] Searching Apollo with criteria: {criteria}")
            mock_response = self._get_mock_people(criteria, page)
            return [self._map_person_to_candidate(p) for p in mock_response["people"]]

        # Build Apollo search request
        search_params: Dict[str, Any] = {
            "page": page,
            "per_page": min(per_page, 100),  # Apollo max is 100
            "reveal_personal_emails": True,  # Request email reveals (costs credits)
            "reveal_phone_number": False,
        }

        # Map our criteria to Apollo's person search parameters
        if criteria.get("titles"):
            search_params["person_titles"] = criteria["titles"]

        if criteria.get("company_sizes"):
            # Apollo uses organization_num_employees_ranges
            search_params["organization_num_employees_ranges"] = criteria["company_sizes"]

        if criteria.get("industries"):
            search_params["organization_industry_tag_ids"] = criteria["industries"]

        if criteria.get("locations"):
            # Apollo supports person_locations
            search_params["person_locations"] = criteria["locations"]

        if criteria.get("seniorities"):
            search_params["person_seniorities"] = criteria["seniorities"]

        if criteria.get("keywords"):
            # Use q_keywords for general keyword search
            search_params["q_keywords"] = " ".join(criteria["keywords"])

        # Additional filters
        if criteria.get("company_names"):
            search_params["organization_names"] = criteria["company_names"]

        if criteria.get("exclude_companies"):
            search_params["organization_not_names"] = criteria["exclude_companies"]

        logger.info(f"Searching Apollo with params: {search_params}")

        response = self._make_request("POST", "mixed_people/api_search", json_data=search_params)

        people = response.get("people", [])
        return [self._map_person_to_candidate(p) for p in people]

    def search_people_paginated(
        self,
        criteria: Dict[str, Any],
        max_results: int = 100,
        per_page: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Search Apollo with automatic pagination to fetch multiple pages.

        Args:
            criteria: Search criteria (same as search_people)
            max_results: Maximum total results to fetch
            per_page: Results per page

        Returns:
            List of all candidate dictionaries up to max_results

        Note:
            This method handles rate limiting by catching ApolloRateLimitError
            and waiting before retrying.
        """
        all_results: List[Dict[str, Any]] = []
        page = 1

        while len(all_results) < max_results:
            try:
                results = self.search_people(criteria, page=page, per_page=per_page)

                if not results:
                    break

                all_results.extend(results)

                if len(results) < per_page:
                    # Last page
                    break

                page += 1

                # Small delay between pages to be respectful
                time.sleep(0.5)

            except ApolloRateLimitError as e:
                logger.warning(f"Rate limited, waiting {e.retry_after}s before retry")
                time.sleep(e.retry_after or 60)
                continue

        return all_results[:max_results]

    def enrich_person(self, linkedin_url: str) -> Dict[str, Any]:
        """
        Get full profile data for a person from their LinkedIn URL.

        Args:
            linkedin_url: LinkedIn profile URL

        Returns:
            Candidate dictionary with enriched profile data

        Raises:
            ApolloRateLimitError: If rate limit is exceeded
            ApolloAPIError: If Apollo API returns an error
        """
        if self.stub_mode:
            logger.info(f"[STUB] Enriching person from LinkedIn: {linkedin_url}")
            # Return mock enriched data
            return {
                "apollo_id": "mock-enriched-001",
                "first_name": "Enriched",
                "last_name": "Person",
                "full_name": "Enriched Person",
                "title": "Senior Benefits Administrator",
                "company": "Enriched Company Inc",
                "company_employee_count": 12000,
                "linkedin_url": linkedin_url,
                "email": "enriched.person@company.com",
                "email_verified": True,
                "region": "Boston, MA, United States",
                "apollo_data": {
                    "organization_id": "mock-org-enriched",
                    "industry": "Healthcare",
                    "seniority": "senior",
                    "departments": ["Human Resources"],
                    "email_status": "verified",
                    "phone_numbers": [],
                }
            }

        logger.info(f"Enriching person from LinkedIn: {linkedin_url}")

        response = self._make_request(
            "POST",
            "people/match",
            json_data={"linkedin_url": linkedin_url}
        )

        person = response.get("person")
        if not person:
            raise ApolloAPIError(404, "Person not found for LinkedIn URL")

        return self._map_person_to_candidate(person)

    def find_email(self, person_id: str) -> Dict[str, Any]:
        """
        Find verified email for a person by their Apollo ID.

        Args:
            person_id: Apollo person ID

        Returns:
            Dictionary with email information:
                - email: The email address (if found)
                - email_status: Status (verified, guessed, unavailable)
                - confidence: Confidence score if available

        Raises:
            ApolloRateLimitError: If rate limit is exceeded
            ApolloAPIError: If Apollo API returns an error
        """
        if self.stub_mode:
            logger.info(f"[STUB] Finding email for person: {person_id}")
            return {
                "email": f"person-{person_id}@example.com",
                "email_status": "verified",
                "confidence": 0.95,
            }

        logger.info(f"Finding email for person: {person_id}")

        # Apollo's people/match endpoint can reveal emails
        response = self._make_request(
            "POST",
            "people/match",
            json_data={"id": person_id, "reveal_personal_emails": False}
        )

        person = response.get("person", {})

        return {
            "email": person.get("email"),
            "email_status": person.get("email_status", "unavailable"),
            "confidence": person.get("email_confidence"),
        }

    def bulk_enrich(
        self,
        linkedin_urls: List[str],
        delay_between_requests: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """
        Enrich multiple people from their LinkedIn URLs.

        Args:
            linkedin_urls: List of LinkedIn profile URLs
            delay_between_requests: Delay in seconds between requests

        Returns:
            List of enriched candidate dictionaries.
            Failed enrichments are logged but not included in results.
        """
        results: List[Dict[str, Any]] = []

        for url in linkedin_urls:
            try:
                enriched = self.enrich_person(url)
                results.append(enriched)
                time.sleep(delay_between_requests)

            except ApolloRateLimitError as e:
                logger.warning(f"Rate limited during bulk enrich, waiting {e.retry_after}s")
                time.sleep(e.retry_after or 60)
                # Retry this URL
                try:
                    enriched = self.enrich_person(url)
                    results.append(enriched)
                except Exception as retry_error:
                    logger.error(f"Failed to enrich {url} after retry: {retry_error}")

            except ApolloAPIError as e:
                logger.error(f"Failed to enrich {url}: {e}")
                continue

        return results


# Singleton instance
_apollo_service: Optional[ApolloService] = None


def get_apollo_service() -> ApolloService:
    """Get or create the Apollo service singleton."""
    global _apollo_service
    if _apollo_service is None:
        _apollo_service = ApolloService()
    return _apollo_service

"""Custom exception hierarchy with error codes for 1ai-reach.

Exception hierarchy:
- OneAIReachException (base)
  - DomainException
    - LeadNotFoundError (LEAD_001)
    - InvalidLeadStatusError (LEAD_002)
    - DuplicateLeadError (LEAD_003)
    - ConversationNotFoundError (CONV_001)
    - InvalidConversationStateError (CONV_002)
    - KnowledgeNotFoundError (KB_001)
    - InvalidKnowledgeError (KB_002)
  - InfrastructureException
    - DatabaseError (DB_001)
    - DatabaseConnectionError (DB_002)
    - DatabaseIntegrityError (DB_003)
    - ExternalAPIError (API_001)
    - APITimeoutError (API_002)
    - APIRateLimitError (API_003)
    - ConfigurationError (CONFIG_001)
    - MissingConfigurationError (CONFIG_002)
  - ApplicationException
    - ValidationError (VAL_001)
    - InvalidInputError (VAL_002)
    - AuthenticationError (AUTH_001)
    - AuthorizationError (AUTH_002)
    - RateLimitError (RATE_001)
"""

from typing import Any, Dict, Optional


class OneAIReachException(Exception):
    """Base exception for all 1ai-reach errors.

    All exceptions in the system inherit from this base class and include:
    - error_code: Programmatic error identifier (e.g., LEAD_001)
    - message: Human-readable error description
    - to_dict(): JSON-serializable representation for API responses
    """

    def __init__(self, message: str, error_code: str, **kwargs: Any) -> None:
        """Initialize exception with message and error code.

        Args:
            message: Human-readable error description
            error_code: Programmatic error identifier
            **kwargs: Additional context data stored in exception
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = kwargs

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to JSON-serializable dictionary.

        Returns:
            Dictionary with error_code, message, type, and context
        """
        return {
            "error_code": self.error_code,
            "message": self.message,
            "type": self.__class__.__name__,
            "context": self.context if self.context else None,
        }

    def __str__(self) -> str:
        """String representation includes error code and message."""
        return f"[{self.error_code}] {self.message}"


# ============================================================================
# DOMAIN EXCEPTIONS - Business logic errors
# ============================================================================


class DomainException(OneAIReachException):
    """Base class for domain-level exceptions.

    Raised when business logic constraints are violated.
    """

    pass


class LeadNotFoundError(DomainException):
    """Raised when a lead cannot be found by ID.

    Error Code: LEAD_001

    Example:
        raise LeadNotFoundError(lead_id="lead_123")
    """

    def __init__(self, lead_id: str) -> None:
        """Initialize with lead ID.

        Args:
            lead_id: The ID of the lead that was not found
        """
        super().__init__(
            message=f"Lead not found: {lead_id}",
            error_code="LEAD_001",
            lead_id=lead_id,
        )
        self.lead_id = lead_id


class InvalidLeadStatusError(DomainException):
    """Raised when attempting invalid lead status transition.

    Error Code: LEAD_002

    Example:
        raise InvalidLeadStatusError(
            current_status="new",
            attempted_status="won",
            reason="Cannot transition directly from new to won"
        )
    """

    def __init__(self, current_status: str, attempted_status: str, reason: str) -> None:
        """Initialize with status transition details.

        Args:
            current_status: Current lead status
            attempted_status: Status being attempted
            reason: Explanation of why transition is invalid
        """
        super().__init__(
            message=f"Invalid status transition from {current_status} to {attempted_status}: {reason}",
            error_code="LEAD_002",
            current_status=current_status,
            attempted_status=attempted_status,
            reason=reason,
        )
        self.current_status = current_status
        self.attempted_status = attempted_status


class DuplicateLeadError(DomainException):
    """Raised when attempting to create a duplicate lead.

    Error Code: LEAD_003

    Example:
        raise DuplicateLeadError(
            email="contact@example.com",
            existing_lead_id="lead_123"
        )
    """

    def __init__(self, email: str, existing_lead_id: str) -> None:
        """Initialize with duplicate lead details.

        Args:
            email: Email of the duplicate lead
            existing_lead_id: ID of the existing lead
        """
        super().__init__(
            message=f"Lead with email {email} already exists (ID: {existing_lead_id})",
            error_code="LEAD_003",
            email=email,
            existing_lead_id=existing_lead_id,
        )
        self.email = email
        self.existing_lead_id = existing_lead_id


class ConversationNotFoundError(DomainException):
    """Raised when a conversation cannot be found.

    Error Code: CONV_001

    Example:
        raise ConversationNotFoundError(conversation_id="conv_456")
    """

    def __init__(self, conversation_id: str) -> None:
        """Initialize with conversation ID.

        Args:
            conversation_id: The ID of the conversation that was not found
        """
        super().__init__(
            message=f"Conversation not found: {conversation_id}",
            error_code="CONV_001",
            conversation_id=conversation_id,
        )
        self.conversation_id = conversation_id


class InvalidConversationStateError(DomainException):
    """Raised when conversation is in invalid state for operation.

    Error Code: CONV_002

    Example:
        raise InvalidConversationStateError(
            conversation_id="conv_456",
            current_state="closed",
            operation="send_message"
        )
    """

    def __init__(
        self, conversation_id: str, current_state: str, operation: str
    ) -> None:
        """Initialize with conversation state details.

        Args:
            conversation_id: The conversation ID
            current_state: Current state of the conversation
            operation: Operation being attempted
        """
        super().__init__(
            message=f"Cannot {operation} on conversation {conversation_id} in state {current_state}",
            error_code="CONV_002",
            conversation_id=conversation_id,
            current_state=current_state,
            operation=operation,
        )
        self.conversation_id = conversation_id
        self.current_state = current_state


class KnowledgeNotFoundError(DomainException):
    """Raised when knowledge base entry is not found.

    Error Code: KB_001

    Example:
        raise KnowledgeNotFoundError(knowledge_id="kb_789")
    """

    def __init__(self, knowledge_id: str) -> None:
        """Initialize with knowledge ID.

        Args:
            knowledge_id: The ID of the knowledge entry that was not found
        """
        super().__init__(
            message=f"Knowledge entry not found: {knowledge_id}",
            error_code="KB_001",
            knowledge_id=knowledge_id,
        )
        self.knowledge_id = knowledge_id


class InvalidKnowledgeError(DomainException):
    """Raised when knowledge entry violates constraints.

    Error Code: KB_002

    Example:
        raise InvalidKnowledgeError(
            knowledge_id="kb_789",
            reason="Category must be one of: service, pain_point, solution"
        )
    """

    def __init__(self, knowledge_id: str, reason: str) -> None:
        """Initialize with knowledge validation details.

        Args:
            knowledge_id: The ID of the knowledge entry
            reason: Explanation of the constraint violation
        """
        super().__init__(
            message=f"Invalid knowledge entry {knowledge_id}: {reason}",
            error_code="KB_002",
            knowledge_id=knowledge_id,
            reason=reason,
        )
        self.knowledge_id = knowledge_id


# ============================================================================
# INFRASTRUCTURE EXCEPTIONS - External system errors
# ============================================================================


class InfrastructureException(OneAIReachException):
    """Base class for infrastructure-level exceptions.

    Raised when external systems (database, APIs, config) fail.
    """

    pass


class DatabaseError(InfrastructureException):
    """Raised when database operation fails.

    Error Code: DB_001

    Example:
        raise DatabaseError(
            operation="insert",
            table="leads",
            reason="Disk quota exceeded"
        )
    """

    def __init__(self, operation: str, table: str, reason: str) -> None:
        """Initialize with database error details.

        Args:
            operation: Database operation that failed (insert, update, delete, select)
            table: Table name involved in the operation
            reason: Explanation of the failure
        """
        super().__init__(
            message=f"Database {operation} on {table} failed: {reason}",
            error_code="DB_001",
            operation=operation,
            table=table,
            reason=reason,
        )
        self.operation = operation
        self.table = table


class DatabaseConnectionError(InfrastructureException):
    """Raised when database connection fails.

    Error Code: DB_002

    Example:
        raise DatabaseConnectionError(
            host="localhost",
            port=5432,
            reason="Connection refused"
        )
    """

    def __init__(self, host: str, port: int, reason: str) -> None:
        """Initialize with connection details.

        Args:
            host: Database host
            port: Database port
            reason: Explanation of the connection failure
        """
        super().__init__(
            message=f"Cannot connect to database at {host}:{port}: {reason}",
            error_code="DB_002",
            host=host,
            port=port,
            reason=reason,
        )
        self.host = host
        self.port = port


class DatabaseIntegrityError(InfrastructureException):
    """Raised when database integrity constraint is violated.

    Error Code: DB_003

    Example:
        raise DatabaseIntegrityError(
            constraint="unique_email",
            table="leads",
            reason="Email already exists"
        )
    """

    def __init__(self, constraint: str, table: str, reason: str) -> None:
        """Initialize with integrity constraint details.

        Args:
            constraint: Name of the constraint violated
            table: Table name
            reason: Explanation of the violation
        """
        super().__init__(
            message=f"Database integrity violation on {table} ({constraint}): {reason}",
            error_code="DB_003",
            constraint=constraint,
            table=table,
            reason=reason,
        )
        self.constraint = constraint
        self.table = table


class ExternalAPIError(InfrastructureException):
    """Raised when external API call fails.

    Error Code: API_001

    Example:
        raise ExternalAPIError(
            service="google_places",
            endpoint="/places/search",
            status_code=500,
            reason="Internal server error"
        )
    """

    def __init__(
        self, service: str, endpoint: str, status_code: int, reason: str
    ) -> None:
        """Initialize with API error details.

        Args:
            service: Name of the external service
            endpoint: API endpoint that was called
            status_code: HTTP status code returned
            reason: Explanation of the error
        """
        super().__init__(
            message=f"External API error from {service} {endpoint}: {status_code} - {reason}",
            error_code="API_001",
            service=service,
            endpoint=endpoint,
            status_code=status_code,
            reason=reason,
        )
        self.service = service
        self.endpoint = endpoint
        self.status_code = status_code


class APITimeoutError(InfrastructureException):
    """Raised when external API call times out.

    Error Code: API_002

    Example:
        raise APITimeoutError(
            service="minerva",
            endpoint="/enrich",
            timeout_seconds=30
        )
    """

    def __init__(self, service: str, endpoint: str, timeout_seconds: int) -> None:
        """Initialize with timeout details.

        Args:
            service: Name of the external service
            endpoint: API endpoint that timed out
            timeout_seconds: Timeout duration in seconds
        """
        super().__init__(
            message=f"API call to {service} {endpoint} timed out after {timeout_seconds}s",
            error_code="API_002",
            service=service,
            endpoint=endpoint,
            timeout_seconds=timeout_seconds,
        )
        self.service = service
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds


class APIRateLimitError(InfrastructureException):
    """Raised when API rate limit is exceeded.

    Error Code: API_003

    Example:
        raise APIRateLimitError(
            service="google_places",
            limit=100,
            window_seconds=3600,
            retry_after_seconds=300
        )
    """

    def __init__(
        self,
        service: str,
        limit: int,
        window_seconds: int,
        retry_after_seconds: Optional[int] = None,
    ) -> None:
        """Initialize with rate limit details.

        Args:
            service: Name of the external service
            limit: Rate limit threshold
            window_seconds: Time window for the limit
            retry_after_seconds: Seconds to wait before retrying (if known)
        """
        super().__init__(
            message=f"Rate limit exceeded for {service}: {limit} requests per {window_seconds}s",
            error_code="API_003",
            service=service,
            limit=limit,
            window_seconds=window_seconds,
            retry_after_seconds=retry_after_seconds,
        )
        self.service = service
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after_seconds = retry_after_seconds


class ConfigurationError(InfrastructureException):
    """Raised when configuration is invalid or incomplete.

    Error Code: CONFIG_001

    Example:
        raise ConfigurationError(
            config_key="DATABASE_URL",
            reason="Invalid PostgreSQL connection string"
        )
    """

    def __init__(self, config_key: str, reason: str) -> None:
        """Initialize with configuration error details.

        Args:
            config_key: Configuration key that is invalid
            reason: Explanation of the configuration issue
        """
        super().__init__(
            message=f"Configuration error for {config_key}: {reason}",
            error_code="CONFIG_001",
            config_key=config_key,
            reason=reason,
        )
        self.config_key = config_key


class MissingConfigurationError(InfrastructureException):
    """Raised when required configuration is missing.

    Error Code: CONFIG_002

    Example:
        raise MissingConfigurationError(
            config_key="WAHA_API_KEY",
            reason="Required for WhatsApp integration"
        )
    """

    def __init__(self, config_key: str, reason: str) -> None:
        """Initialize with missing configuration details.

        Args:
            config_key: Configuration key that is missing
            reason: Explanation of why it's required
        """
        super().__init__(
            message=f"Missing required configuration: {config_key} ({reason})",
            error_code="CONFIG_002",
            config_key=config_key,
            reason=reason,
        )
        self.config_key = config_key


# ============================================================================
# APPLICATION EXCEPTIONS - API and validation errors
# ============================================================================


class ApplicationException(OneAIReachException):
    """Base class for application-level exceptions.

    Raised for validation, authentication, and rate limiting issues.
    """

    pass


class ValidationError(ApplicationException):
    """Raised when input validation fails.

    Error Code: VAL_001

    Example:
        raise ValidationError(
            field="email",
            value="invalid-email",
            reason="Invalid email format"
        )
    """

    def __init__(self, field: str, value: Any, reason: str) -> None:
        """Initialize with validation error details.

        Args:
            field: Field name that failed validation
            value: Value that failed validation
            reason: Explanation of the validation failure
        """
        super().__init__(
            message=f"Validation failed for {field}: {reason}",
            error_code="VAL_001",
            field=field,
            value=str(value),
            reason=reason,
        )
        self.field = field
        self.value = value


class InvalidInputError(ApplicationException):
    """Raised when input is invalid or malformed.

    Error Code: VAL_002

    Example:
        raise InvalidInputError(
            input_type="json",
            reason="Missing required field: lead_id"
        )
    """

    def __init__(self, input_type: str, reason: str) -> None:
        """Initialize with invalid input details.

        Args:
            input_type: Type of input that is invalid (json, csv, etc.)
            reason: Explanation of what is invalid
        """
        super().__init__(
            message=f"Invalid {input_type} input: {reason}",
            error_code="VAL_002",
            input_type=input_type,
            reason=reason,
        )
        self.input_type = input_type


class AuthenticationError(ApplicationException):
    """Raised when authentication fails.

    Error Code: AUTH_001

    Example:
        raise AuthenticationError(
            auth_method="api_key",
            reason="Invalid or expired API key"
        )
    """

    def __init__(self, auth_method: str, reason: str) -> None:
        """Initialize with authentication error details.

        Args:
            auth_method: Authentication method that failed
            reason: Explanation of the authentication failure
        """
        super().__init__(
            message=f"Authentication failed ({auth_method}): {reason}",
            error_code="AUTH_001",
            auth_method=auth_method,
            reason=reason,
        )
        self.auth_method = auth_method


class AuthorizationError(ApplicationException):
    """Raised when user lacks required permissions.

    Error Code: AUTH_002

    Example:
        raise AuthorizationError(
            user_id="user_123",
            resource="lead_456",
            required_permission="edit_lead"
        )
    """

    def __init__(self, user_id: str, resource: str, required_permission: str) -> None:
        """Initialize with authorization error details.

        Args:
            user_id: ID of the user attempting the action
            resource: Resource being accessed
            required_permission: Permission that is required
        """
        super().__init__(
            message=f"User {user_id} lacks permission {required_permission} for {resource}",
            error_code="AUTH_002",
            user_id=user_id,
            resource=resource,
            required_permission=required_permission,
        )
        self.user_id = user_id
        self.resource = resource
        self.required_permission = required_permission


class RateLimitError(ApplicationException):
    """Raised when application rate limit is exceeded.

    Error Code: RATE_001

    Example:
        raise RateLimitError(
            user_id="user_123",
            limit=100,
            window_seconds=3600,
            retry_after_seconds=300
        )
    """

    def __init__(
        self,
        user_id: str,
        limit: int,
        window_seconds: int,
        retry_after_seconds: Optional[int] = None,
    ) -> None:
        """Initialize with rate limit details.

        Args:
            user_id: ID of the user hitting the limit
            limit: Rate limit threshold
            window_seconds: Time window for the limit
            retry_after_seconds: Seconds to wait before retrying (if known)
        """
        super().__init__(
            message=f"Rate limit exceeded for user {user_id}: {limit} requests per {window_seconds}s",
            error_code="RATE_001",
            user_id=user_id,
            limit=limit,
            window_seconds=window_seconds,
            retry_after_seconds=retry_after_seconds,
        )
        self.user_id = user_id
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after_seconds = retry_after_seconds

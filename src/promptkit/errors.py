"""PromptKit exceptions."""


class PromptKitError(Exception):
  """Base exception for PromptKit errors."""


class PromptSpecError(PromptKitError):
  """Raised when promptspec.yaml is invalid."""


class PromptRenderError(PromptKitError):
  """Raised when prompt rendering fails."""


class PromptReleaseError(PromptKitError):
  """Raised when a release cannot be created."""


class PromptLoadError(PromptKitError):
  """Raised when a released prompt cannot be loaded."""

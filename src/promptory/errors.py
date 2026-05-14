"""Promptory exceptions."""


class PromptoryError(Exception):
  """Base exception for Promptory errors."""


class PromptSpecError(PromptoryError):
  """Raised when promptspec.yaml is invalid."""


class PromptRenderError(PromptoryError):
  """Raised when prompt rendering fails."""


class PromptReleaseError(PromptoryError):
  """Raised when a release cannot be created."""


class PromptLoadError(PromptoryError):
  """Raised when a released prompt cannot be loaded."""

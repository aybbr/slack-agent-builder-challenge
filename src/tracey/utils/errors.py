def error_response(asset_id: str, message: str, **extra: object) -> dict[str, object]:
    """Return a standardized error response dict.

    All service functions use this helper to ensure callers receive
    a consistent shape: ``{"asset_id": ..., "error": ..., ...}``.

    Args:
        asset_id: The asset identifier that was being queried.
        message: Human-readable error description.
        **extra: Additional context fields (e.g. ``column_name``).

    Returns:
        A dict with at least ``asset_id`` and ``error`` keys.

    Example:
        >>> error_response("fct_sales_pipeline", "Manifest not found")
        {"asset_id": "fct_sales_pipeline", "error": "Manifest not found"}

        >>> error_response("fct_sales_pipeline", "Invalid column",
        ...                column_name="lead_score")
        {"asset_id": "fct_sales_pipeline", "error": "Invalid column",
         "column_name": "lead_score"}
    """
    return {"asset_id": asset_id, "error": message, **extra}

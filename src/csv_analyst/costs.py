"""Display cumulative Managed Agents list cost in USD cents."""


def format_cost(cents: int | None) -> str:
    if cents is None:
        return "cost pending"
    return f"${cents / 100:.2f} list cost"

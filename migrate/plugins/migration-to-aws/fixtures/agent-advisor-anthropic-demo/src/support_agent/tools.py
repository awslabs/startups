"""Local tools used by the support agent."""


ORDERS = {
    "A-100": {"status": "shipped", "carrier": "Parcel Express"},
    "A-200": {"status": "processing", "carrier": None},
}

ARTICLES = {
    "refund": "Refunds are available within 30 days of delivery.",
    "shipping": "Standard shipping normally takes 3-5 business days.",
}


def lookup_order(order_id):
    return ORDERS.get(order_id, {"status": "not_found", "carrier": None})


def search_help_center(query):
    normalized = query.lower()
    matches = [
        {"topic": topic, "content": content}
        for topic, content in ARTICLES.items()
        if topic in normalized or normalized in content.lower()
    ]
    return {"matches": matches}


def execute_tool(name, arguments):
    if name == "lookup_order":
        return lookup_order(arguments["order_id"])
    if name == "search_help_center":
        return search_help_center(arguments["query"])
    raise ValueError(f"unsupported tool: {name}")

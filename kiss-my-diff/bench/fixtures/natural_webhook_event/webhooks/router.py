def route_event(event):
    handlers = {
        "invoice_paid": "billing",
        "customer_created": "crm",
    }
    return handlers.get(event["type"], "unknown")

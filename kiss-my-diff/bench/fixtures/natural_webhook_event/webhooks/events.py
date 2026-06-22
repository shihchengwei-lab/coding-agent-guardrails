ALIASES = {
    "invoice.paid": "invoice_paid",
    "customer.created": "customer_created",
}


def normalize_event(value):
    return ALIASES.get(value, value)

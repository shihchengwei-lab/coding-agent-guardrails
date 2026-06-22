def find_by_phone(customers, phone):
    for customer in customers:
        if customer["phone"] == phone:
            return customer
    return None

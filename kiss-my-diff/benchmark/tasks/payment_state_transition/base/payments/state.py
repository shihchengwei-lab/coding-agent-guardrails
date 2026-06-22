def apply_event(state, event):
    if event == "authorize":
        return "authorized"
    if event == "capture":
        return "captured"
    if event == "cancel":
        return "canceled"
    if event == "refund":
        return "refunded"
    return state

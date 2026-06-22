from orders.importer import order_totals


def test_totals_basic_rows():
    csv_text = "order_id,sku,quantity,price\nA1,pen,2,1.50\nA1,bag,1,3.00\nB2,pin,4,0.25\n"

    assert order_totals(csv_text) == {"A1": 600, "B2": 100}


def test_ignores_blank_lines():
    csv_text = "order_id,sku,quantity,price\nA1,pen,2,1.50\n\n"

    assert order_totals(csv_text) == {"A1": 300}


def test_quoted_sku_with_comma():
    csv_text = 'order_id,sku,quantity,price\nA1,"large, blue bag",2,3.00\n'

    assert order_totals(csv_text) == {"A1": 600}

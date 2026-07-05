from orders.importer import order_totals


def test_quoted_fields_and_thousands_separator():
    csv_text = (
        "order_id,sku,quantity,price\n"
        'A1,"large, blue bag",2,"$1,200.50"\n'
        'A1,"gift wrap",1,"$3.25"\n'
        'B2,"pin",3,"$0.99"\n'
    )

    assert order_totals(csv_text) == {"A1": 240425, "B2": 297}

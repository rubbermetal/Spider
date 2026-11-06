"""
Module to validate the optional per-seed limit fields of the seed forms.

Usage example:
    form = {"max_depth": "5", "max_pages": "100", "recrawl_hours": "24", "allow_external": "yes"}
    values, errors = parse_limits(form)
    print(values)  # {'max_depth': 5, 'max_pages': 100, 'recrawl_hours': 24, 'allow_external': True}
    print(errors)  # {}
"""

def _whole(text, low, high):
    try:
        value = int(text)
        if value < low or value > high:
            raise ValueError
        return value
    except ValueError:
        raise ValueError(f"must be a whole number between {low} and {high}")

def parse_limits(form):
    values = {}
    errors = {}

    fields = {
        "max_depth": (0, 50),
        "max_pages": (1, 10000000),
        "recrawl_hours": (1, 87600),
        "allow_external": None
    }

    for field, bounds in fields.items():
        value = form.get(field, "").strip()
        if field == "allow_external":
            if value == "":
                values[field] = None
            elif value == "yes":
                values[field] = True
            elif value == "no":
                values[field] = False
            else:
                errors[field] = "choose default, yes or no"
                values[field] = None
        else:
            low, high = bounds
            if value == "":
                values[field] = None
            else:
                try:
                    values[field] = _whole(value, low, high)
                except ValueError as e:
                    errors[field] = str(e)
                    values[field] = None

    return values, errors

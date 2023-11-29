def parse_fio(input_str):
    input_str = input_str.split(' ')
    if len(input_str) < 2:
        return None
    return input_str[0], input_str[1]


def parse_height(input_str):
    try:
        if float(input_str) <= 0:
            return None
        return float(input_str)
    except (ValueError, TypeError):
        return None

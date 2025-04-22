


def test_func(parameter_name, parameter_output_values, value):
    if parameter_name in parameter_output_values:
                try:
                    parameter_output_values[parameter_name] = parameter_output_values[parameter_name] + value
                except TypeError:
                    try:
                        parameter_output_values[parameter_name].append(value)
                    # except AttributeError:
                    #     pass
                        #TODO(kate): figure out how to handle this case
                    except Exception as e:
                        msg = f"Value is not appendable to parameter '{parameter_name}'"
                        raise ValueError(msg) from e
    else:
        parameter_output_values[parameter_name] = value


parameter_name = "test1"
parameter_output_values={"test1":[1,2,3]}
value = 4
test_func(parameter_name, parameter_output_values, value)
print(parameter_output_values)
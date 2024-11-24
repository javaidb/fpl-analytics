import sys
from src.functions.data_exporter import output_data_to_json, grab_path_relative_to_root

def calculate_mean_std_dev(data):
    mean = sum(data) / len(data)
    var = sum((l - mean) ** 2 for l in data) / len(data)
    st_dev = math.sqrt(var)

    return mean, st_dev

def progress_bar_update(i, num_iter, complete=False):
    if not complete:
        sys.stdout.write(f'\rProcessing {i+1}/4 ' + '.' * (num_iter % 4) + '   ')
    else:
        sys.stdout.write('\rProcessing... \x1b[32m\u2714\x1b[0m\n')
    sys.stdout.flush()

def initialize_local_data(instance, data_list, update_and_export_data = False):

    """
    Function used to import from local data AND choose to either update it from relevant API endpoints before importing or not
    (Option chosen as API endpoints such as UnderStat can be computationally expensive if running every time)

    Parameters:
    - data_list (list): List that contains the following format:
        [{
                "function": <ENTER FUNCTION NAME>,
                "attribute_name": <ENTER ATTRIBUTE NAME>,
                "file_name": <ENTER FILE NAME>,
                "export_path": <ENTER DIRECTORY TO FILE>,
                "update_bool_override": <[OPTIONAL] ENTER UPDATE BOOL FOR SPECIFIC SET TO OVERRIDE GENERAL SETTING>
        }]
    - update_and_export_data (bool): Description of parameter2.

    Returns:
    - N/A: Initializes variables, does not return anything.
    """

    for item in data_list:
        function = item.get('function')
        attribute = item.get('attribute_name')
        file_path = item.get('export_path')
        file_name = item.get('file_name')
        if "update_bool_override" in item.keys():
            custom_update_bool = item.get('update_bool_override')
        else: custom_update_bool = None
        file_path_written = grab_path_relative_to_root(file_path, absolute=True, create_if_nonexistent=True)
        full_path = f'{file_path_written}/{file_name}.json'

        if function and attribute and file_path:
            if update_and_export_data or not os.path.exists(full_path) or custom_update_bool:
                data = function()
                output_data_to_json(data, full_path)
            else:
                with open(full_path, 'r') as file:
                    data = json.load(file)
            setattr(instance, attribute, data)
import os
import json

def output_data_to_json(data, file_path):
    with open(file_path, 'w') as json_file:
        json.dump(data, json_file)

def grab_path_relative_to_root(path_from_root: str, relative=False, absolute=False, create_if_nonexistent=False):
    """
    Find the path provided from the root, whether it is relative to the current location or from the drive (such as C:), and create if not found.
    The root in this case is considered as the name of the git repository that houses other folders.
    
    Args:
    - path_from_root (str): The path relative to the 'src' directory to ensure existence for.

    Returns:
    - str: The concatenated path to the directory provided from root.
    """
    root_path, rel_path_to_root = _find_paths_to_root()

    if relative:
        return _ensure_directory_exists(os.path.join(rel_path_to_root, path_from_root)) if create_if_nonexistent else os.path.join(rel_path_to_root, path_from_root)
    elif absolute:
        return _ensure_directory_exists(os.path.join(root_path, path_from_root)) if create_if_nonexistent else os.path.join(rel_path_to_root, path_from_root)
    else: print("One of 'absolute' or 'relative' needs to be True")

def _find_paths_to_root():
    """
    Find the root directory and the relative path from the current location to the root directory.

    Returns:
    - tuple: A tuple containing the full path to the root directory and the relative path to the root directory.
    """

    cwd = os.getcwd()

    root_path = ""
    rel_path_to_root = ""

    # Traverse up the directory tree until the root directory is found
    while cwd != os.path.dirname(cwd):
        # Check if 'src' is in the current directory as a marker
        if "src" in os.listdir(cwd):
            root_path = cwd
            break
        rel_path_to_root = os.path.join("..", rel_path_to_root)
        cwd = os.path.dirname(cwd)

    return root_path, rel_path_to_root

def _ensure_directory_exists(full_path: str) -> str:
    """
    Ensure that the directory structure for the given path exists relative to the 'src' directory.
    If the directory does not exist, create it.
    
    Args:
    - full_path (str): The full path provided from 'grab_path' function.
    
    Returns:
    - str: The absolute path to the directory.
    """
    
    if not os.path.exists(full_path):
        os.makedirs(full_path)
    
    return full_path

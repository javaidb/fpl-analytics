import ipywidgets as widgets
from IPython.display import display, clear_output

def create_search_widget(entries):
    search_box = widgets.Text(
        description='Search:',
        placeholder='Type to search...',
        layout=widgets.Layout(width='300px')
    )
    
    output = widgets.Output()

    def on_search(change):
        with output:
            clear_output()
            search_term = change['new']
            
            if search_term == "*":
                print("All entries:")
                if isinstance(entries, dict):
                    for key, value in entries.items():
                        print(f"{key}: {value}")
                elif isinstance(entries, list):
                    for entry in entries:
                        print(entry)
            elif search_term:
                print(f"Results for '{search_term}':")
                if isinstance(entries, dict):
                    matches = {key: value for key, value in entries.items() if search_term.lower() in key.lower()}
                    if matches:
                        for key, value in matches.items():
                            print(f"{key}: {value}")
                    else:
                        print("No matching keys found.")
                elif isinstance(entries, list):
                    matches = [entry for entry in entries if search_term.lower() in entry.lower()]
                    if matches:
                        for match in matches:
                            print(f"{match}")
                    else:
                        print("No matching entries found.")
            else:
                print("Please enter a search term or '*' to see all options.")

    search_box.observe(on_search, names='value')
    display(search_box, output)

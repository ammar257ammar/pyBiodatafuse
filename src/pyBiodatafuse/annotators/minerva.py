# coding: utf-8

"""Python file for queriying the MINERVA platform (https://minerva.pages.uni.lu/doc/)."""

import datetime
import warnings
from typing import Optional, Tuple

import pandas as pd
import requests

from pyBiodatafuse.utils import collapse_data_sources, get_identifier_of_interest


def check_endpoint_minerva(endpoint: Optional[str] = None) -> bool:
    """Check the availability of the MINERVA API endpoint.

    :param endpoint: MINERVA API endpoint ("https://minerva-net.lcsb.uni.lu/api")
    :returns: True if the endpoint is available, False otherwise.
    """
    endpoint = endpoint if endpoint is not None else "https://minerva-net.lcsb.uni.lu/api"

    response = requests.get(endpoint + "/machines/")

    # Check if API is down
    if response.status_code == 200:
        return True
    else:
        return False


def get_version_minerva(map_endpoint: str) -> dict:
    """Get version of minerva API.

    :param map_endpoint: MINERVA map API endpoint ("https://covid19map.elixir-luxembourg.org/minerva/")
    :returns: a dictionary containing the version information
    """
    response = requests.get(map_endpoint + "api/configuration/")

    conf_dict = response.json()
    minerva_version = {"minerva_version": conf_dict["version"]}

    return minerva_version


def list_projects(endpoint: Optional[str] = None) -> pd.DataFrame:
    """Get information about MINERVA projects.

    :param endpoint: MINERVA API endpoint ("https://minerva-net.lcsb.uni.lu/api/")
    :returns: a DataFrame containing url, names, and IDs from the different projects in MINERVA plattform
    """
    endpoint = endpoint if endpoint is not None else "https://minerva-net.lcsb.uni.lu/api"

    response = requests.get(endpoint + "/machines/")
    projects = response.json()
    projects_ids = projects["pageContent"]
    project_df = pd.DataFrame()
    for x in projects_ids:
        entry = {"url": x["rootUrl"], "id": x["id"]}
        entry_df = pd.DataFrame([entry])
        project_df = pd.concat([project_df, entry_df], ignore_index=True)

    map_id_list = []
    names_list = []
    for x in project_df["id"]:
        x = str(x)
        if len(requests.get(endpoint + "/machines/" + x + "/projects/").json()["pageContent"]) != 0:
            map_id = requests.get(endpoint + "/machines/" + x + "/projects/").json()["pageContent"][
                0
            ]["projectId"]
            name = requests.get(endpoint + "/machines/" + x + "/projects/").json()["pageContent"][
                0
            ]["mapName"]
            map_id_list.append(map_id)
            names_list.append(name)
        else:
            project_df = project_df[
                project_df["id"] != int(x)
            ]  # If pageContent is not present, then delete this entry

    project_df["map_id"] = map_id_list
    project_df["names"] = names_list

    return project_df


def get_minerva_components(
    map_name: str,
    endpoint: Optional[str] = None,
    get_elements: Optional[bool] = True,
    get_reactions: Optional[bool] = True,
) -> Tuple[str, dict]:
    """Get information about MINERVA componenets from a specific project.

    :param endpoint: MINERVA API endpoint ("https://minerva-net.lcsb.uni.lu/api/")
    :param map_name: name of the map you want to retrieve the information from. At the moment the options are:
        'Asthma Map' 'COVID19 Disease Map' 'Expobiome Map' 'Atlas of Inflammation Resolution' 'SYSCID map'
        'Aging Map' 'Meniere's disease map' 'Parkinson's disease map' 'RA-Atlas'
    :param get_elements: if get_elements = True,
        the elements of the model will appear as a dictionary in the output of the function
    :param get_reactions: if get_reactions = True,
        the reactions of the model will appear as a dictionary in the output of the function

    :returns: a Dictionary containing two other dictionaries (map_elements and map_reactions) and a list (models).
        - 'map_elements' contains a list for each of the pathways in the model.
            Those lists provide information about Compartment, Complex, Drug, Gene, Ion, Phenotype,
            Protein, RNA and Simple molecules involved in that pathway
        - 'map_reactions' contains a list for each of the pathways in the model.
            Those lists provide information about the reactions involed in that pathway.
        - 'models' is a list containing pathway-specific information for each of the pathways in the model
    """
    endpoint = endpoint if endpoint is not None else "https://minerva-net.lcsb.uni.lu/api"
    # Get list of projects
    project_df = list_projects(endpoint)
    # Get url from the project specified
    condition = project_df["names"] == map_name
    row = project_df.index[condition].tolist()
    map_url = project_df.loc[row, "url"].to_string(index=False, header=False)
    project_id = project_df.loc[row, "map_id"].to_string(index=False, header=False)

    # Request project data using the extracted project ID
    response = requests.get(map_url + "/api/projects/" + project_id + "/models/")

    models = (
        response.json()
    )  # pull down only models and then iterate over them to extract element of interest
    map_components = {"models": models}

    if get_elements:
        # Get elements of the chosen diagram
        model_elements = {}
        for model in models:
            model = str(model["idObject"])
            url_complete = (
                map_url
                + "api/projects/"
                + project_id
                + "/models/"
                + model
                + "/"
                + "bioEntities/elements/"
            )
            response_data = requests.get(url_complete)
            model_elements[model] = response_data.json()
        map_components["map_elements"] = model_elements

    if get_reactions:
        # Get reactions of the chosen diagram
        model_reactions = {}
        for model in models:
            model = str(model["idObject"])
            url_complete = (
                map_url
                + "api/projects/"
                + project_id
                + "/models/"
                + model
                + "/"
                + "bioEntities/reactions/"
            )
            response_data = requests.get(url_complete)
            model_reactions[model] = response_data.json()
        map_components["map_reactions"] = model_reactions

    return map_url, map_components


def get_gene_minerva_pathways(
    bridgedb_df: pd.DataFrame,
    map_name: str,
    input_type: Optional[str] = "Protein",
    endpoint: Optional[str] = None,
    get_elements: Optional[bool] = True,
    get_reactions: Optional[bool] = True,
) -> Tuple[pd.DataFrame, dict]:
    """Get information about MINERVA pathways associated with a gene.

    :param bridgedb_df: BridgeDb output for creating the list of gene ids to query
    :param map_name: name of the map you want to retrieve the information from. At the moment the options are:
        'Asthma Map' 'COVID19 Disease Map' 'Expobiome Map' 'Atlas of Inflammation Resolution' 'SYSCID map'
        'Aging Map' 'Meniere's disease map' 'Parkinson's disease map' 'RA-Atlas'
    :param endpoint: MINERVA API endpoint ("https://minerva-net.lcsb.uni.lu/api/")
    :param input_type: 'Compartment','Complex', 'Drug', 'Gene', 'Ion','Phenotype','Protein','RNA','Simple molecule'
    :param get_elements: if get_elements = True,
        the elements of the model will appear as a dictionary in the output of the function
    :param get_reactions: if get_reactions = True,
        the reactions of the model will appear as a dictionary in the output of the function

    :returns: a DataFrame containing DataFrame containing the MINERVA output and dictionary of the MINERVA metadata.
    """
    endpoint = endpoint if endpoint is not None else "https://minerva-net.lcsb.uni.lu/api"
    # Check if the MINERVA API is available
    api_available = check_endpoint_minerva(endpoint=endpoint)
    if not api_available:
        warnings.warn(
            "MINERVA API endpoint is not available. Unable to retrieve data.", stacklevel=2
        )
        return pd.DataFrame(), {}

    # Record the start time
    start_time = datetime.datetime.now()

    map_url, map_components = get_minerva_components(
        endpoint=endpoint, map_name=map_name, get_elements=get_elements, get_reactions=get_reactions
    )
    map_elements = map_components.get("map_elements", {})
    models = map_components.get("models", {})

    data_df = get_identifier_of_interest(bridgedb_df, "NCBI Gene")

    names = []
    for value in models:
        name = value["name"]
        names.append(name)

    row = 1
    combined_df = pd.DataFrame()
    for x in names:
        index_to_extract = row
        row = 1 + row

        list_at_index = list(map_elements.values())[index_to_extract - 1]
        common_keys = ["type", "references", "symbol", "name"]
        # Initialize empty lists to store values for each common key
        type = []
        refs = []
        symbol = []
        name = []

        # Iterate through the list of dicts
        for d in list_at_index:
            for key in common_keys:
                if key in d:
                    if key == "type":
                        type.append(d[key])
                    elif key == "references":
                        refs.append(d[key])
                    elif key == "symbol":
                        symbol.append(d[key])
                    elif key == "name":
                        name.append(d[key])

        data = pd.DataFrame()
        data["symbol"] = symbol
        data["pathwayLabel"] = x
        data["pathwayGeneCount"] = len(symbol) - symbol.count(None)
        data["pathwayId"] = models[index_to_extract - 1]["idObject"]
        data["refs"] = refs
        data["type"] = type

        combined_df = pd.concat([combined_df, data], ignore_index=True)
        combined_df = combined_df[combined_df["type"] == input_type]

    # Record the end time
    end_time = datetime.datetime.now()

    if "symbol" not in combined_df:
        return pd.DataFrame()
    else:
        # Add MINERVA output as a new column to BridgeDb file
        combined_df.rename(columns={"symbol": "identifier"}, inplace=True)
        combined_df["identifier"] = combined_df["identifier"].values.astype(str)
        combined_df = combined_df.drop_duplicates(subset=["identifier", "pathwayId"])
        selected_columns = ["pathwayId", "pathwayLabel", "pathwayGeneCount"]

        # Merge the two DataFrames based on 'gene_id', 'gene_symbol', 'identifier', and 'target'
        merged_df = collapse_data_sources(
            data_df=data_df,
            source_namespace="NCBI Gene",
            target_df=combined_df,
            common_cols=["identifier"],
            target_specific_cols=selected_columns,
            col_name="MINERVA",
        )

        """Metdata details"""
        # Get the current date and time
        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Calculate the time elapsed
        time_elapsed = str(end_time - start_time)
        # Add version to metadata file
        minerva_version = get_version_minerva(map_endpoint=map_url)
        # Add the datasource, query, query time, and the date to metadata
        minerva_metadata = {
            "datasource": "MINERVA",
            "metadata": {"source_version": minerva_version},
            "query": {
                "size": data_df["target"].nunique(),
                "input_type": "NCBI Gene",
                "MINERVA project": map_name,
                "time": time_elapsed,
                "date": current_date,
                "url": map_url,
            },
        }

    return merged_df, minerva_metadata

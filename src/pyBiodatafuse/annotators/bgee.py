#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Python file for queriying Bgee database (https://bgee.org)."""

import datetime
import os
import warnings
from string import Template

import pandas as pd
from SPARQLWrapper import JSON, SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import SPARQLWrapperException

from pyBiodatafuse.constants import BGEE, BGEE_ENDPOINT
from pyBiodatafuse.utils import collapse_data_sources, get_identifier_of_interest


def check_endpoint_bgee() -> bool:
    """Check the availability of the Bgee SPARQL endpoint.

    :returns: True if the endpoint is available, False otherwise.
    """
    with open(os.path.dirname(__file__) + "/queries/bgee-get-last-modified.rq", "r") as fin:
        sparql_query = fin.read()

    sparql = SPARQLWrapper(BGEE_ENDPOINT)
    sparql.setReturnFormat(JSON)

    sparql.setQuery(sparql_query)

    try:
        sparql.queryAndConvert()
        return True
    except SPARQLWrapperException:
        return False


def get_version_bgee() -> dict:
    """Get version of Bgee RDF data from its SPARQL endpoint.

    # not sure if a version per-se can be retrieved, but the endpoint supports
    # http://purl.org/dc/terms/modified
    :returns: a dictionary containing the last modified date information
    """
    with open(os.path.dirname(__file__) + "/queries/bgee-get-last-modified.rq", "r") as fin:
        sparql_query = fin.read()

    sparql = SPARQLWrapper(BGEE_ENDPOINT)
    sparql.setReturnFormat(JSON)

    sparql.setQuery(sparql_query)
    res = sparql.queryAndConvert()

    bgee_version = {"bgee_version": res["results"]["bindings"][0]["date_modified"]["value"]}

    return bgee_version


def get_gene_expression(bridgedb_df: pd.DataFrame):
    """Query gene-tissue expression information from Bgee.

    :param bridgedb_df: BridgeDb output for creating the list of gene ids to query
    :returns: a DataFrame containing the Bgee output and dictionary of the Bgee metadata.
    """
    # Check if the DisGeNET API is available
    api_available = check_endpoint_bgee()

    if not api_available:
        warnings.warn(
            f"{BGEE} SPARQL endpoint is not available. Unable to retrieve data.", stacklevel=2
        )
        return pd.DataFrame(), {}

    # Record the start time
    start_time = datetime.datetime.now()

    data_df = get_identifier_of_interest(bridgedb_df, "Ensembl")
    gene_list = data_df["target"].tolist()
    gene_list = list(set(gene_list))

    query_gene_lists = []
    if len(gene_list) > 25:
        for i in range(0, len(gene_list), 25):
            tmp_list = gene_list[i : i + 25]
            query_gene_lists.append(" ".join(f'"{g}"' for g in tmp_list))

    else:
        query_gene_lists.append(" ".join(f'"{g}"' for g in gene_list))

    anat_entities_list = """
    blood
    bone marrow
    brain
    breast
    cardiovascular system
    digestive system
    heart
    immune organ
    kidney
    liver
    lung
    nervous system
    pancreas
    placenta
    reproductive system
    respiratory system
    skeletal system
    """

    anatomical_entities_list = anat_entities_list.split("\n")
    anatomical_entities_list = [
        anatomical_entity.strip()
        for anatomical_entity in anatomical_entities_list
        if anatomical_entity.strip() != ""
    ]

    with open(
        os.path.dirname(__file__) + "/queries/bgee-genes-tissues-expression-level.rq", "r"
    ) as fin:
        sparql_query = fin.read()

    sparql = SPARQLWrapper(BGEE_ENDPOINT)
    sparql.setReturnFormat(JSON)

    query_count = 0

    intermediate_df = pd.DataFrame()

    for gene_list_str in query_gene_lists:
        query_count += 1

        sparql_query_template = Template(sparql_query)

        for anatomical_entity in anatomical_entities_list:
            # for the query text, need to put each name in between quotes
            anatomical_entity = f'"{anatomical_entity}"'
            substit_dict = dict(gene_list=gene_list_str, anat_entities_list=anatomical_entity)
            sparql_query_template_sub = sparql_query_template.substitute(substit_dict)

            sparql.setQuery(sparql_query_template_sub)
            res = sparql.queryAndConvert()

            df = pd.DataFrame(res["results"]["bindings"])

            df = df.applymap(lambda x: x["value"])

            intermediate_df = pd.concat([intermediate_df, df], ignore_index=True)

    # Record the end time
    end_time = datetime.datetime.now()

    # Organize the annotation results as an array of dictionaries
    intermediate_df.rename(columns={"ensembl_id": "target"}, inplace=True)
    intermediate_df["anatomical_entity_id"] = intermediate_df["anatomical_entity_id"].apply(
        lambda x: x.split("/")[-1]
    )
    intermediate_df["developmental_stage_id"] = intermediate_df["developmental_stage_id"].apply(
        lambda x: x.split("/")[-1]
    )

    # Metadata details
    # Get the current date and time
    current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate the time elapsed
    time_elapsed = str(end_time - start_time)

    # Add version to metadata file
    bgee_version = get_version_bgee()

    # Add the datasource, query, query time, and the date to metadata
    bgee_metadata = {
        "datasource": BGEE,
        "metadata": {"source_version": bgee_version},
        "query": {
            "size": len(gene_list),
            "time": time_elapsed,
            "date": current_date,
            "url": BGEE_ENDPOINT,
        },
    }

    # Merge the two DataFrames on the target column
    merged_df = collapse_data_sources(
        data_df=data_df,
        source_namespace="Ensembl",
        target_df=intermediate_df,
        common_cols=["target"],
        target_specific_cols=[
            "anatomical_entity_id",
            "anatomical_entity_name",
            "developmental_stage_id",
            "developmental_stage_name",
            "expression_level",
            "confidence_level",
        ],
        col_name=BGEE,
    )

    return merged_df, bgee_metadata

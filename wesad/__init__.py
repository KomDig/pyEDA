import pathlib
import pickle
import zipfile
from io import BytesIO

import pandas as pd

from tqdm import tqdm
import requests

_WESAD_FILE = (pathlib.Path(__file__).parent / 'wesad.zip').absolute()
_WESAD_DIR = pathlib.Path(__file__).parent / 'WESAD'

_headers = {
    "ACC": ["TS", "X", "Y", "Z"],
    "EDA": [
        "TS",
        "EDA",
    ],
    "BVP": [
        "TS",
        "BVP",
    ],
    "TEMP": [
        "TS",
        "TEMP",
    ],
    "HR": [
        "TS",
        "HR",
    ],
    "IBI": [
        "T",
        "DT",
    ],
    "tags": [
        0,
    ],
}


class WESADException(Exception):
    pass


def download_wesad():
    """Downloads the WESAD dataset and extracts it"""
    if not _WESAD_DIR.exists() and not _WESAD_FILE.exists():
        print("Downloading data...")
        url = "https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx/download"  # big file test
        # Streaming, so we can iterate over the response.
        response = requests.get(url, stream=True)
        total_size_in_bytes = int(response.headers.get('content-length', 0))
        block_size = 1024  # 1 Kilobyte
        progress_bar = tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True)
        with open(str(_WESAD_FILE), 'wb') as file:
            for data in response.iter_content(block_size):
                progress_bar.update(len(data))
                file.write(data)
        progress_bar.close()

        if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
            raise ValueError("ERROR, something went wrong")
    else:
        print("WESAD zipfile already exists.")

    if not _WESAD_DIR.exists():
        with zipfile.ZipFile(_WESAD_FILE) as zf:
            print("Extracting data...")
            zf.extractall(_WESAD_FILE.parent)
    else:
        print("WESAD folder already exists.")


def load_synced_data_for_subject(subject_nbr):

    subject_folder = _WESAD_DIR / f"S{subject_nbr}"
    if not subject_folder.exists():
        raise WESADException(f"Subject {subject_nbr} does not exist. Possible numbers are 2-11 and 13-17.")

    # Regular pickle did not work. Seems to be pickled with pandas...
    # with open(subject_folder / f"S{subject_nbr}.pkl", "rb") as f:
    #     data = pickle.loads(f.read())
    # Using pandas pickling
    data = pd.read_pickle(str(subject_folder / f"S{subject_nbr}.pkl"))
    return data


def load_empatica_data_for_subject(subject_nbr):
    """Load the Empatica data for one subject.

    Parameters
    ----------
    subject_nbr : int
        the id for the subject to load data from

    Returns
    -------
    data : dict
        dictionary with all recorded signals as pandas DataFrames

    """
    subject_folder = _WESAD_DIR / f"S{subject_nbr}"
    if not subject_folder.exists():
        raise WESADException(f"Subject {subject_nbr} does not exist. Possible numbers are 2-11 and 13-17.")
    subject_file = subject_folder / f"S{subject_nbr}_E4_Data.zip"
    return _load_empatica_connect_zip_file(subject_file)


def _load_empatica_connect_zip_file(file):
    """Load an Empatica E4 zip file to a dict.

    Args:
        file: Either the path to the file, or a file-like object.
          If it is a path, the file will be opened and closed by the method.

    Returns:
        A dictionary of all signals.

    """
    output = {}
    with zipfile.ZipFile(file) as zf:
        for f in filter(lambda x: x.filename.endswith(".csv"), zf.filelist):
            raw = zf.read(f).splitlines()
            if f.filename.startswith("tags"):
                data = pd.DataFrame([pd.Timestamp(float(r), unit="s") for r in raw])
            else:
                if not f.filename.startswith("IBI"):
                    dt = float(raw[0].split(b",")[0])
                    fq = int(float(raw[1].split(b",")[0]))
                    data: pd.DataFrame = pd.read_csv(
                        BytesIO(b"\n".join(raw[2:])),
                        header=None,
                        names=_headers.get(f.filename.replace(".csv", ""))[1:],
                    )
                    dt_range = pd.date_range(
                        pd.Timestamp(dt, unit="s"),
                        periods=len(data),
                        freq=f"{int(1 / fq * 1e6)}U",
                    )
                    data.set_index(dt_range, inplace=True)
                else:
                    fq = None
                    data: pd.DataFrame = pd.read_csv(
                        BytesIO(b"\n".join(raw[1:])),
                        header=None,
                        names=_headers.get(f.filename.replace(".csv", "")),
                    )
                    dt_range = pd.DatetimeIndex(
                        data=[pd.Timestamp(t, unit="s") for t in data["T"] + dt]
                    )
                    data.set_index(dt_range, inplace=True)
            output[f.filename.replace(".csv", "")] = data
            if fq:
                output[f.filename.replace(".csv", "") + " Frequency"] = fq
    return output

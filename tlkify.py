from typing import Dict, List # For advanced type hints.
from glob import glob         # For batch file operations.
import pandas as pd           # For advanced data manipulation.
import contextlib             # For safely removing files.
import subprocess             # For calling the compiler.
import shutil                 # For OS-agnostic file operations.
import json                   # For storing script hashes.
import sys                    # For command line arguments.
import os                     # For OS-level operations.

class IOHelper():
    '''A collection of helpers for reading and writing 2DA, TLK and JSON label files.'''

    def __init__(self, nwn_erf : str, nwn_tlk : str) -> None:
        '''Initializes an IO object with the given paths to the NWN_Erf and NWN_Tlk binaries.'''
        # Validate the given paths.
        if not os.path.exists(nwn_erf):
            print(f'Error: Unable to locate nwn_erf at "{nwn_erf}"') ; exit(1)
        if not os.path.exists(nwn_tlk):
            print(f'Error: Unable to locate nwn_tlk at "{nwn_tlk}"') ; exit(1)
        # Store the binary paths for later use.
        self.nwn_erf = nwn_erf
        self.nwn_tlk = nwn_tlk

    @staticmethod
    def read_labels(json_path : str, silent_warnings : bool = False) -> pd.DataFrame:
        '''Reads a JSON file containing TLK labels and returns it as a pandas DataFrame.'''
        if not os.path.isfile(json_path) or not json_path.lower().endswith('.json'):
            return pd.DataFrame()
        # Attempt to read the JSON file using different encodings.
        for encoding in ['utf-8', 'utf-8-sig']:
            try:
                df = pd.read_json(json_path, encoding=encoding)
                break
            except ValueError:
                continue
        if 'id' not in df.columns:
            raise ValueError(f'Unable to proceed due to missing ID column in JSON file: {json_path}')
        df['id'] = df['id'].astype(int)
        df.set_index('id', inplace=True)
        # sort the index to ensure it is in ascending order.
        df.sort_index(inplace=True)
        # Check for duplicates in the index.
        if not silent_warnings and df.index.duplicated().any():
            # Keep the last occurrence of each duplicate index and warn the user.
            print(f'W: {os.path.basename(json_path)}: Duplicate entries for 2DA row(s): {df.index[df.index.duplicated()].tolist()}')
            df = df[~df.index.duplicated(keep='last')]
        return df

    @staticmethod
    def read_2da(file_path : str, validate_index : bool = True) -> pd.DataFrame:
        '''Converts a 2DA file to a pandas DataFrame.'''
        if not os.path.isfile(file_path) or not file_path.lower().endswith('.2da'):
            raise FileNotFoundError(f'Unable to proceed due to invalid 2DA file path: {file_path}')
        try:
            df = pd.read_csv(file_path, encoding='ISO-8859-1',
                             sep=r'\s+', quotechar='"',
                             skiprows=2, index_col=0)
        except pd.errors.ParserError as e:
            print(f'E: {os.path.basename(file_path)}: {str(e).replace("C error: ", "")}\nStopping TLK generation on first error.\n\n1 error; see above for context.\n\nProcessing aborted.')
            exit(1)
        if validate_index and not df.index.is_monotonic_increasing:
            # Ensure that the index is an ascending range of integers.
            print(f'W: {os.path.basename(file_path)}: Row indices not in ascending order. Reindexing...')
            df.reset_index(inplace=True)
        df.index.name = 'id'
        return df

    @staticmethod
    def write_2da(df_2da : pd.DataFrame, file_path : str) -> None:
        "Writes a DataFrame representing 2DA contents to a 2DA file."
        # Export the DataFrame to a CSV file.
        df_2da.to_csv(file_path, sep=' ', quotechar='"', index_label='')
        # Append the generated CSV file to the 2DA header.
        text = '2DA V2.0\n\n'
        with open(file_path, 'r') as f:
            text += f.read().strip()
        # Then overwrite the original 2DA file with the updated text.
        with open(file_path, 'w') as f:
            f.write(text + '\n')

    def write_hak(self, input_directory : str, output_path : str) -> None:
        '''Packages the contents of a directory into a HAK file.'''
        # Ensure the given directory is valid.
        if not os.path.isdir(input_directory):
            raise FileNotFoundError(f'Unable to proceed due to invalid directory: {input_directory}')
        # Package the directory into a HAK file using nwn_erf.
        subprocess.run([self.nwn_erf,
                        '-e', 'HAK',           # Override ERF header type to HAK.
                        '-c', input_directory, # Create archive from input files or directories.
                        '-f', output_path])    # Operate on FILE instead of stdin/out

class TLK():
    '''A class representing the contents of a TLK file.'''

    # Define the temporary directory and file for TLK operations.
    TEMP_DIR  = os.path.join(os.path.split(__file__)[0], 'tmp', '.tlkify')
    TEMP_FILE = os.path.join(TEMP_DIR, f'.tmp.json')

    # An offset that differentiates custom TLK entries from standard ones.
    OFFSET = 16777216

    def __init__(self, input_2da_folder : str, input_json_folder  : str, io_helper : IOHelper) -> None:
        '''Initializes an empty TLK object.'''
        # Validate the given IOHelper object.
        if not isinstance(io_helper, IOHelper):
            raise ValueError(f'Invalid IOHelper object provided: {io_helper}')
        self.io = io_helper

        # Ensure the temporary directory exists.
        os.makedirs(TLK.TEMP_DIR, exist_ok=True)

        # Store the input directories.
        self.input_2das  = input_2da_folder
        self.input_json  = input_json_folder
        # TLK values are stored as a dictionary with 'language' and 'entries' keys.
        # - The 'language' key is an integer representing the language of the TLK file.
        # - The 'entries' key is a list of dictionaries with 'id' and 'text' keys.
        self.values = {
            'language': 0,
            'entries': []
        }
        # We'll cache entries to avoid duplicates.
        self.existing = {}
        # To keep track of empty keys, we store a list of them.
        self.blanks = set()

    def __len__(self) -> int:
        '''Returns the number of entries in this TLK.'''
        # The length of a TLK is the number of entries it contains.
        return len(self.values['entries'])

    def __repr__(self) -> str:
        '''Returns a string representation of this TLK object.'''
        # Create a table of the TLK contents.
        content_table = [str({entry["id"]: entry['text'].replace('\n', '\\n')})[1:-1]
                         for entry in self.values['entries']]
        return ',\n'.join(content_table)

    def __add_item__(self, id : int, text : str) -> None:
        '''Internal function. Adds a new entry to this TLK instance.'''
        # TLK contents are stored as a list of dictionaries with 'id' and 'text' keys.
        self.existing[text] = id + TLK.OFFSET
        self.values['entries'].append({
            'id': id,
            'text': text
        })

    def add(self, text : str) -> int:
        '''Adds a new entry to this TLK instance and returns its ID.'''
        # If the text already exists, return its cached ID.
        if text in self.existing:
            return self.existing[text]

        # TLK contents are stored as a list of dictionaries with 'id' and 'text' keys.
        id = self.blanks.pop() if self.blanks else len(self)
        self.__add_item__(id, text)
        return self.existing[text]

    def add_id(self, id : int, text : str) -> int:
        '''Adds a new entry to this TLK instance with the given ID. This ID must exceed the current maximum.'''
        # Ensure the given ID is valid.
        max_value = max(self.existing.values()) - TLK.OFFSET if len(self.existing) > 0 else 0
        if max_value and id <= max_value:
            raise ValueError(f'ID {id} must be greater than the current maximum of {max_value}.')

        # Add the new entry to the list of entries, then add the range of missing IDs to the blanks set.
        self.__add_item__(id, text)
        self.blanks.update(range(max_value + 1, id))
        return self.existing[text]

    def add_2da_labels(self, name : str, spell_name_desc_offset : int = 5000) -> pd.DataFrame:
        '''Updates this TLK object with the contents of a 2DA DataFrame.'''
        # Load the 2DA and JSON files.
        df_2da  = IOHelper.read_2da(os.path.join(self.input_2das, f'{name}.2da'))
        df_json = IOHelper.read_labels(os.path.join(self.input_json, f'{name}.json'))
        df_json = self.add_missing_labels(name, df_2da, df_json)

        # Drop any columns that are not in the 2DA file.
        df_json = df_json[df_json.columns.intersection(df_2da.columns)]
        if df_json.empty:
            return df_2da

        # Spells.2da has a different structure, so we'll handle it separately.
        if name == 'spells':
            return self.add_spell_labels(df_2da, df_json, spell_name_desc_offset)

        # Generate TLK references for all columns, then update the 2DA file.
        df_json = df_json.map(self.add, na_action='ignore')
        df_2da.update(df_json, overwrite=True)
        return df_2da

    def add_spell_labels(self, df_2da : pd.DataFrame, df_json : pd.DataFrame, name_desc_offset : int) -> pd.DataFrame:
        '''Updates this TLK object with the contents of the spells.2da DataFrame.'''
        # If a name_desc_offset was specified, assign static Name and SpellDesc IDs in the TLK file.
        STATIC_COLUMNS = ('Name', 'SpellDesc') if name_desc_offset > 0 else ()

        # Most columns can be handled normally.
        for column in df_json.columns.difference(STATIC_COLUMNS):
            df_json[column] = df_json[column].map(self.add, na_action='ignore')
        df_2da.update(df_json, overwrite=True)

        if not STATIC_COLUMNS:
            return df_2da

        # Determine static IDs via the 2DA row index and column order.
        df_ids = pd.DataFrame(index=df_json.index)
        for i, column in enumerate(STATIC_COLUMNS):
            df_ids[column] = name_desc_offset + i + len(STATIC_COLUMNS) * df_ids.index
            df_ids[column] = df_ids[column].where(df_json[column].notna(), df_json[column])

        # Update this TLK with df_id's ids and df_json's TLK strings.
        all(self.add_id(id=getattr(row, column),
                        text=df_json.at[row[0], column])
            for row in df_ids.itertuples()
            for column in STATIC_COLUMNS
            if pd.notna(getattr(row, column)))

        # Update the 2DA file with the new TLK references.
        df_2da.update(df_ids + TLK.OFFSET, overwrite=True)
        return df_2da

    def add_missing_labels(self, name : str, df_2da : pd.DataFrame, df_json : pd.DataFrame) -> pd.DataFrame:
        '''Updates the given JSON label DataFrame with additional lowercase, plural and/or adjective forms.'''
        if name == 'classes':
            # Add plural and lowercase labels for classes, using 'Name' as a reference.
            if 'Name' not in df_json.columns:
                print(f'W: {name}.json: Unable to add additional labels. Missing "Name" column.')
                return df_json
            # Ensure the required columns exist before proceeding.
            if 'Plural' not in df_json.columns:
                df_json['Plural'] = pd.Series()
            # Add missing labels to the JSON file.
            df_json['Plural'] = df_json['Plural'].where(df_json['Plural'].notna(), df_json['Name']
                                                 .map(TLK.__dynamic_plural__, na_action='ignore'))
            df_json['Lower'] = df_json['Name'].str.lower()
        elif name == 'racialtypes':
            # Add plural and lowercase labels for races, using 'Name' as a reference.
            if 'Name' not in df_json.columns:
                print(f'W: {name}.json: Unable to add additional labels. Missing "Name" column.')
                return df_json
            # Ensure the required columns exist before proceeding.
            if 'NamePlural' not in df_json.columns:
                df_json['NamePlural'] = pd.Series()
            if 'ConverName' not in df_json.columns:
                df_json['ConverName'] = pd.Series()
            if 'ConverNameLower' not in df_json.columns:
                df_json['ConverNameLower'] = pd.Series()
            # Add missing labels to the JSON file.
            df_json['NamePlural'] = df_json['NamePlural'].where(df_json['NamePlural'].notna(), df_json['Name']
                                                         .map(TLK.__dynamic_plural__, na_action='ignore'))
            df_json['ConverName'] = df_json['ConverName'].where(df_json['ConverName'].notna(), df_json['Name']
                                                         .map(TLK.__dynamic_adjective, na_action='ignore'))
            df_json['ConverNameLower'] = df_json['ConverNameLower'].where(df_json['ConverNameLower'].notna(), df_json['ConverName'].str.lower())
            df_json['ConverNameLower'] = df_json['ConverNameLower'].where(df_json['ConverNameLower'].notna(), df_json['Name'].str.lower())
        elif name == 'iprp_spells':
            try:
                # Load spells.2da and spells.json to reference spell names. Exclude feat spells and abilities.
                df_spells = IOHelper.read_labels(os.path.join(self.input_json, f'spells.json'), silent_warnings=True).join(
                            IOHelper.read_2da(os.path.join(self.input_2das, f'spells.2da')), rsuffix='_2da')[['Name', 'FeatID', 'UserType']]
                df_spells = df_spells[(df_spells['FeatID'] == '****') & (df_spells['UserType'] == '1')]
            except FileNotFoundError:
                print(f'W: spells.2da: File not found. iprp_spells may be missing labels.')
                return df_json
            # Before making any significant adjustments, remember the original columns.
            if 'Name' not in df_json.columns:
                df_json['Name'] = pd.Series()
            original_columns = df_json.columns.to_list()
            df_json = df_json.reindex(df_2da.index)

            # Create columns to join the JSON file with the 2DA file on.
            df_spells['SpellIndex'] = df_spells.index.astype(int)
            df_json['SpellIndex'] = df_2da['SpellIndex'].replace('****', -1).astype(int)
            df_json = df_json.merge(df_spells, on='SpellIndex', how='left', suffixes=('', '_spells'))
            # Drop entries with missing SpellIndex values.
            df_json = df_json[df_json['SpellIndex'] != -1]

            # Add missing labels to the JSON file.
            df_json['Name'] = df_json['Name'].where(df_json['Name'].notna(),
                                                    df_json['Name_spells'] + ' (' + df_2da['CasterLvl'] + ')')
            df_json = df_json[df_json['Name'].str.contains(r'\*{4}', na=True) == False][original_columns]
        elif name == 'iprp_feats':
            # Load feat.json to reference feat names.
            df_feats = IOHelper.read_labels(os.path.join(self.input_json, f'feat.json'), silent_warnings=True)[['FEAT']]
            # Before making any significant adjustments, remember the original columns.
            if 'Name' not in df_json.columns:
                df_json['Name'] = pd.Series()
            original_columns = df_json.columns.to_list()
            df_json = df_json.reindex(df_2da.index)

            # Create columns to join the JSON file with the 2DA file on.
            df_feats['FeatIndex'] = df_feats.index.astype(int)
            df_json['FeatIndex'] = df_2da['FeatIndex'].replace('****', -1).astype(int)
            df_json = df_json.merge(df_feats, on='FeatIndex', how='left')
            # Drop entries with missing FeatIndex values.
            df_json = df_json[df_json['FeatIndex'] != -1]
            # Add missing labels to the JSON file.
            df_json['Name'] = df_json['Name'].where(df_json['Name'].notna(), df_json['FEAT'])
            df_json = df_json[original_columns]
        return df_json

    @staticmethod
    def __dynamic_plural__(text : str) -> str:
        '''Returns a basic plural form of the given noun.'''
        match text[-2:]:
            case 'ch', 'is', 'sh':   return text + 'es'       # 'Witch' -> 'Witches'
            case 'fe':               return text[:-2] + 'ves' # 'Wife' -> 'Wives'
            case 'lf':               return text[:-1] + 'ves' # 'Elf' -> 'Elves'
        match text[-1]:
            case 's', 'x', 'z', 'o': return text + 'es'       # 'Class' -> 'Classes'
            case 'f':                return text[:-1] + 'ves' # 'Dwarf' -> 'Dwarves'
            case 'y':
                if text[-2] not in 'aeiou':
                    return text[:-1] + 'ies'                  # 'City' -> 'Cities'
        return text + 's'

    @staticmethod
    def __dynamic_adjective(text : str) -> str:
        '''Returns a basic adjective form of the given noun.'''
        match text[-1]:
            case 'f': return text[:-1] + 'ven' # 'Elf' -> 'Elven'
        return text

    def to_tlk(self, tlk_path : str) -> None:
        '''Exports this TLK object to a TLK file.'''
        # Sort the entries by ID before exporting.
        self.values['entries'].sort(key=lambda entry: entry['id'])
        # To export a TLK file, we first need to create a temporary JSON file.
        with open(TLK.TEMP_FILE, 'w') as file:
            json.dump(self.values, file)
        # Once the JSON file exists, we can convert it to a TLK using the NWN_TLK.
        subprocess.run([self.io.nwn_tlk,
                        '-i', TLK.TEMP_FILE, # Input file [default: -]
                        '-o', tlk_path])    # Output file [default: -]
        # Safely remove the temporary JSON file.
        TLK.__remove_temp_file__()

    @staticmethod
    def __remove_temp_file__():
        '''Removes the temporary JSON file if it exists.'''
        with contextlib.suppress(FileNotFoundError):
            os.remove(TLK.TEMP_FILE)

    @staticmethod
    def from_tlk(tlk_path : str, input_2da_folder : str, input_json_folder  : str, io_helper : IOHelper) -> 'TLK':
        '''Creates a TLK object from a TLK file.'''
        # Ensure the given path is valid.
        if not os.path.isfile(tlk_path) or not tlk_path.lower().endswith('.tlk'):
            # The file path is invalid.
            raise FileNotFoundError(f'Unable to proceed due to invalid TLK file path: {tlk_path}')

        # Safely remove the temporary JSON file.
        TLK.__remove_temp_file__()
        # Convert the TLK file to a JSON file using the NWN_TLK.
        subprocess.run([io_helper.nwn_tlk,
                        '-i', tlk_path,
                        '-o', TLK.TEMP_FILE])
        if not os.path.isfile(TLK.TEMP_FILE):
            # An error occurred during the conversion.
            raise FileNotFoundError('Failed to convert TLK file.')
        # If the file was successfully converted, import it.
        with open(TLK.TEMP_FILE, 'r') as file:
            tlk = TLK(input_2da_folder = input_2da_folder,
                      input_json_folder = input_json_folder,
                      io_helper = io_helper)
            tlk.values = json.load(file)
            tlk.existing = {entry['text']: entry['id']
                            for entry in tlk.values['entries']}
            # Find any missing ids and add them to the list of blanks. We'll fill them in later.
            tlk.blanks = {id for id in range(max(tlk.existing.values()))
                          if id not in tlk.existing.values()}
        TLK.__remove_temp_file__()
        return tlk

    @staticmethod
    def from_json(json_path : str, input_2da_folder : str, input_json_folder  : str, io_helper : IOHelper) -> 'TLK':
        '''Creates a TLK object from a JSON file.'''
        # Ensure the given path is valid.
        if not os.path.isfile(json_path) or not json_path.lower().endswith('.json'):
            raise FileNotFoundError(f'Unable to proceed due to invalid JSON file path: {json_path}')
        with open(json_path, 'r') as file:
            # Load and validate the JSON file.
            values = json.load(file)
            if len(values.keys()) != 2 or not ('language' in values and 'entries' in values):
                raise ValueError(f'Unable to proceed due to invalid JSON format: {values.keys()}')
            # The JSON file is valid. Create a new TLK instance and import the values.
            tlk = TLK(input_2da_folder = input_2da_folder,
                      input_json_folder = input_json_folder,
                      io_helper = io_helper)
            tlk.values = values
            tlk.existing = {entry['text']: entry['id']
                            for entry in tlk.values['entries']}
            # Find any missing ids and add them to the list of blanks. We'll fill them in later.
            tlk.blanks = {id for id in range(max(tlk.existing.values()))
                          if id not in tlk.existing.values()}
            return tlk

class TlkBuilder():
    '''A class for combining 2DA files and JSON labels to TLK files.'''

    def __init__(self,
        io_helper         : IOHelper,
        static_2da_folder : str,
        input_2da_folder  : str,
        input_json_folder : str,
        output_folder     : str|List[str] = 'output',
        output_tlk_name   : str = 'output.tlk',
        output_hak_name   : str = 'output.hak',
        tlk_reference     : str = '',
        spell_offset      : int = 5000,
        ) -> None:
        '''Initializes a new TlkBuilder instance.'''

        # Validate the given parameters.
        if not os.path.exists(static_2da_folder):
            print(f'Error: Unable to locate static 2DA directory at "{static_2da_folder}"') ; exit(1)
        if not os.path.exists(input_2da_folder):
            print(f'Error: Unable to locate input 2DA directory at "{input_2da_folder}"') ; exit(1)
        if not os.path.exists(input_json_folder):
            print(f'Error: Unable to locate input JSON directory at "{input_json_folder}"') ; exit(1)
        if tlk_reference and not os.path.exists(tlk_reference):
            print(f'Error: Unable to locate specified TLK reference at "{tlk_reference}"') ; exit(1)
        # Validate the given IOHelper object.
        if not isinstance(io_helper, IOHelper):
            raise ValueError(f'Invalid IOHelper object provided: {io_helper}')
        if spell_offset < 0:
            raise ValueError(f'Spell offset must be a positive integer, got {spell_offset}')

        # Store the input and output directories.
        self.static_2das = static_2da_folder
        self.input_2das  = input_2da_folder
        self.input_json  = input_json_folder
        self.output_dir  = output_folder[0] if isinstance(output_folder, list) else output_folder
        self.hak_name    = output_hak_name
        self.tlk_name    = output_tlk_name
        self.io          = io_helper

        # Initialize the TLK object with initial labels, if provided.
        if tlk_reference:
            if tlk_reference.endswith('.tlk'):
                self.tlk = TLK.from_tlk(tlk_reference, input_2da_folder, input_json_folder, io_helper=io_helper)
            elif tlk_reference.endswith('.json'):
                self.tlk = TLK.from_json(tlk_reference, input_2da_folder, input_json_folder, io_helper=io_helper)
            else:
                raise ValueError(f'Invalid TLK reference file provided: {tlk_reference}')
        else:
            self.tlk = TLK(input_2da_folder, input_json_folder, io_helper=io_helper)

        # Process all 2DA files, then create the HAK and TLK.
        processed_2das = self.process_2das(spell_name_desc_offset=spell_offset)
        self.write_output(processed_2das)

        if isinstance(output_folder, list) and len(output_folder) > 1:
            for folder in output_folder[1:]:
                try:
                    # If multiple output directories are provided, copy the output files to each of them.
                    shutil.copy(os.path.join(self.output_dir, 'hak', self.hak_name), os.path.join(folder, 'hak', self.hak_name))
                    shutil.copy(os.path.join(self.output_dir, 'tlk', self.tlk_name), os.path.join(folder, 'tlk', self.tlk_name))
                except shutil.SameFileError:
                    # Likely a symlink. Skip it.
                    continue
        exit(0)

    def process_2das(self, spell_name_desc_offset : int = 5000) -> Dict[str, pd.DataFrame]:
        '''Processes a 2DA file and updates the TLK object.'''
        print('Generating TLK references...')
        # Parse all 2DA files and update the TLK with their JSON strings.
        processed = {os.path.basename(file): self.tlk.add_2da_labels(os.path.basename(file)[:-4], spell_name_desc_offset)
                     for file in sorted(glob(os.path.join(self.input_2das, f'*.2da')))}
        # Also load 2DA files without corresponding json files to clear their whitespace and validate them.
        processed.update({os.path.basename(file): IOHelper.read_2da(file, validate_index=False)
                          for file in sorted(glob(os.path.join(self.static_2das, f'*.2da')))})
        return processed

    def write_output(self, updated_2das : Dict[str, pd.DataFrame]) -> None:
        '''Writes the updated TLK and 2DA files to the output directory.'''
        # Write the updated TLK and 2DA files to the output directory.
        self.tlk.to_tlk(os.path.join(self.output_dir, 'tlk', self.tlk_name))
        for name, df in updated_2das.items():
            IOHelper.write_2da(df, os.path.join(TLK.TEMP_DIR, name))

        # Package the output directory into a HAK file, then wipe the temporary directory.
        self.io.write_hak(TLK.TEMP_DIR, os.path.join(self.output_dir, 'hak', self.hak_name))
        shutil.rmtree(TLK.TEMP_DIR)

if __name__ == '__main__':
    # Run TlkBuilder in the current directory.
    script_directory = os.path.split(__file__)[0]
    helper = IOHelper(
        nwn_erf=os.path.join(script_directory, 'nwn_erf.exe' if sys.platform == 'win32' else 'nwn_erf'),
        nwn_tlk=os.path.join(script_directory, 'nwn_tlk.exe' if sys.platform == 'win32' else 'nwn_tlk'),
    )
    TlkBuilder(
        static_2da_folder = os.path.join(script_directory, 'static_2da'),
        input_2da_folder  = os.path.join(script_directory, 'input_2da'),
        input_json_folder = os.path.join(script_directory, 'input_json'),
        io_helper = helper,
    )

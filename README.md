# ARE_Tlkify
A Python-based TLK builder used in development workflows on the [Arelith persistent role playing server](https://nwnarelith.com).

### Motivation
TLKs (talk tables) are lookup tables used within the Neverwinter Nights engine. They map individual integers (so-called 'string references') to localised text. Generally, adding new TLK entries requires specialised tools and additional, manual adjustments within the 2DA files that point at these references. This makes changes hard to track and, since invalid entries create no errors beyond bad text labels, potentially difficult to troubleshoot. This utility automates the process, addressing these issues.

### Main Features
- Combines 2DA files with TLK labels assigned within identically-named JSON files.
- Generates a dynamic TLK entry for each label and updates the 2DA row with the new string reference.
- Packages the processed 2DA files into one HAK file and generates a new TLK.

### Additional Features
- Adds additional TLK entries such as:
  - Missing plurals, adjectives and lowercase forms for `racialtypes.2da` and `classes.2da` entries that a `Name` has been provided for in the JSON file.
  - Missing item property labels for `iprp_spells.2da` and `iprp_feats.2da` entries that **no** `Name` has been provided for in the JSON file.
    - These labels are retrieved from `spells.2da` and `feat.2da`, respectively.
    - For `iprp_spells.2da`, it also appends the caster level of the item property.
- Maps spell names and descriptions specified in `spells.json` to a static, row-dependent string reference. This ensures that item blueprints (such as scrolls) referencing these TLK texts need not be updated after generating a new TLK file.
- Avoids duplicate TLK entries for identical strings and removes unneeded 2DA whitespace, thereby reducing output size.
- Validates all 2DAs, including the ones in `static_2da_folder`, before building the HAK file.

### File Structure
- 2DA files: As usual. All rows that have no matching `id` in the JSON file remain unchanged.
- JSON files: A list of dictionaries.
  - Each dictionary represents a 2DA row.
  - The dictionary's `id` key represents the 2DA row number, all other keys the 2DA column names to be modified.

Example: `spells.json`
```json
[
   {
      "id": 1234,
      "Name":"Renamed Spell - Preserves the original description." 
   },
   {
      "id": 1235,
      "Name":"Custom Spell",
      "SpellDesc":"This entry will overwrite both the spell's name and description."
   },
   {
      "id": 1236,
      "SpellDesc":"A spell whose name will be preserved, while the original description gets replaced with this text."
   }
]
```

### Requirements
- ARE_Tlkify is compatible with Python version 3.11 or newer. The only additional Python dependency is [Pandas](https://pandas.pydata.org) (version 2.2.0 or newer).
- Uses `nwn_tlk` and `nwn_erf` from [neverwinter.nim](https://github.com/niv/neverwinter.nim) to import/export TLK files and package the modified 2DA files into a HAK.

### Configuration
The default input directories are called `input_2da`, `input_json` and `static_2da`. If needed, use the following parameters to adjust this.
| TlkBuilder Param                      | Description                                                                                                                    |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `input_2da_folder`                    | A folder containing all 2DA files you'd like to generate new string references for.                                            |
| `input_json_folder`                   | A folder containing a JSON file for each 2DA file in `input_2da_folder`. These files contain the TLK entries for your 2DAs.    |
| `static_2da_folder`                   | A folder containing all 2DA files that need no additional string references, but should be included in the output HAK file.    |
| `tlk_reference`                       | An optional path to a TLK or JSON file containing initial string references. Tlkify will expand them with its own references.  |
| `output_tlk_name` / `output_hak_name` | The file names of generated HAK and TLK files. [Default values: `output.hak` and `output.tlk`]                                 |
| `output_folder`                       | The folder these two files will be written to. Can be a list of multiple paths. [Default value: `output`]                      |
| `spell_offset`                        | An offset of all custom TLK entries for spells.2da. Creates replicable string references across multiple runs. [Default: 5000] |
| `io_helper`                           | IOHelper object (see below). Specifies paths to the required binaries `nwn_erf` and `nwn_tlk` from neverwinter.nim.            |

By default, ARE_Tlkify looks for `nwn_erf` and `nwn_tlk` binaries in the same folder as the TLK Builder script. The IOHelper class can customise this behaviour.
| IOHelper Param | Description                                            |
| -------------- | ------------------------------------------------------ |
| `nwn_erf`      | The path to the `nwn_erf` binary from neverwinter.nim. |
| `nwn_tlk`      | The path to the `nwn_tlk` binary from neverwinter.nim. |

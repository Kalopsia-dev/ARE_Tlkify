# ARE_Tlkify
A Python-based TLK builder used in development workflows on the [Arelith persistent role playing server](https://nwnarelith.com).

### Motivation
TLKs (talk tables) are lookup tables used within the Neverwinter Nights engine. They map individual integers (so-called 'string references') to localised text. Generally, adding new TLK entries requires specialised tools and additional, manual adjustments within the 2DA files that point at these references. This makes changes hard to track and, since invalid entries create no errors beyond bad text labels, potentially difficult to troubleshoot. This utility automates the process, addressing these issues.

### Main Features
- Combines the provided 2DA files with their corresponding JSON files.
- Generates dynamic TLK entries for each provided JSON string and updates its corresponding 2DA entry with the correct reference.
- Packages the resulting 2DA files into one HAK file and generates a new TLK.

### Additional Features
- Adds additional TLK entries such as:
  - Missing plurals, adjectives and lowercase forms for `racialtypes.2da` and `classes.2da` entries that a `Name` has been provided for in the corresponding JSON file.
  - Missing item property labels for `iprp_spells.2da` and `iprp_feats.2da` entries that **no** `Name` has been provided for in the corresponding JSON file.
    - These labels are retrieved from `spells.2da` and `feat.2da`, respectively.
    - For `iprp_spells.2da`, it also appends the caster level of the item property.
- Maps spell names and descriptions specified in `spells.json` to a static, row-dependent string reference. This ensures that item blueprints (such as scrolls) referencing these TLK texts need not be updated after generating a new TLK file.
- Avoids duplicate TLK entries for identical strings and removes unneeded 2DA whitespace, thereby reducing output size.
- Validates all 2DAs, including the ones in `STATIC_2DA_DIR`, before building the HAK file.

### File Structure
- 2DA files: As usual. All entries that have no match in the corresponding JSON file remain unchanged.
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

### Environment Constants
In order for Tlkify to work correctly, the following environment constants may need to be modified in `tlkify.py`:
| Directory Constant                 | Description                                                                                                                     |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `INPUT_2DA_DIR`                    | A folder containing all 2DA files you'd like to generate new string references for.                                             |
| `INPUT_JSON_DIR`                   | A folder containing a JSON file for each 2DA file in `INPUT_2DA_DIR`. These JSON files contain the TLK entries for your 2DAs.   |
| `STATIC_2DA_DIR`                   | A folder containing all 2DA files that need no additional string references, but should be included in the output HAK file.     |
| `SERVER_DIR`                       | The configuration folder of your `nwserver` instance. Must contain `hak` and `tlk` folders.                                     |
| `USER_DIR`                         | The configuration folder of your NWN client (usually located in the Documents directory). Must contain `hak` and `tlk` folders. |
| `TEMP_DIR`                         | A folder for `tlkify` to temporarily store its processed files in.                                                              |
| `AREDEV_DIR`                       | The parent folder of your module.                                                                                               |

| File Name Constant                 | Description                                                                                                                     |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `ORIGINAL_TLK`                     | The path to a TLK or JSON file containing initial string references. Tlkify will expand them.                                   |
| `NWN_ERF`                          | The path to the `nwn_erf` binary from neverwinter.nim.                                                                          |
| `NWN_TLK`                          | The path to the `nwn_tlk` binary from neverwinter.nim.                                                                          |

### Requirements
- ARE_Tlkify is compatible with Python version 3.11 or newer. The only additional Python dependency is [Pandas](https://pandas.pydata.org) (version 2.2.0 or newer).
- Uses `nwn_tlk` and `nwn_erf` from [neverwinter.nim](https://github.com/niv/neverwinter.nim) to import/export TLK files and package the modified 2DA files into a HAK.

### Usage
Update the environment constants above to match your own project's folder structure, then run `tlkify.py`.

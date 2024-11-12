# PostgreSQL Network Tools

# Table of Contents 
- [PostgreSQL Network Tools](#postgresql-network-tools)
- [Table of Contents](#table-of-contents)
- [Overview](#overview)
  - [File Breakdown](#file-breakdown)
- [Usage](#usage)
  - [Notes](#notes)
  - [Setup](#setup)

# Overview
This repo is dedicated to housing some utilities I've built to explore intersections between Python-based network automation and PostgreSQL database interactions.

> :warning: Use these scripts at your own risk. These have not been thoroughly tested against any specific hardware/software releases. See [LICENSE](./LICENSE) for details.

> :warning: Always test code in a safe test environment before using in production environments!

## File Breakdown

| filename | purpose |
| --- | --- |
| .env.template | Use this as a template for filling out your .env file. The .env file is used for storing sensitive variables in your ENV_VARS. |
| .gitignore | Tells git what files to ignore tracking on. |
| LICENSE | Legal license for this codebase. |
| README.md | The file you're reading right now! |
| collect_eigrp.py | Script used for collecting information from EIGRP-speaking routers and storing metadata in PSQL database. |
| logging.conf | Logging configuration for the Python logging library. Currently unused, will use in future. |
| requirements.txt | Used by pip to automatically install all Python dependencies. | 
| sql_test.py | Simple python script to test out custom SQL queries. Handy to use while developing. | 

# Usage

## Notes
- You must have a [dedicated PostgreSQL server built](https://www.postgresql.org/docs/16/tutorial-install.html) for this code to interact with. 
- This code was developed using [Python v3.12.5](https://www.python.org/downloads/release/python-3125/)

## Setup

1. [Clone this repository](https://github.com/git-guides/git-clone) to your machine.
   
2. Create a python virtual environment to contain all the code dependencies:

    ```
    # Windows CMD
    cd local-path-to-cloned-repo
    python -m venv .
    ```

3. Install all python dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Add all relevant variables to [the .env file.](https://github.com/dakotah-hurda/psql-testing/blob/main/.env.template) Make sure to rename the .env.template file to simply '.env'. 

    > :warning: NEVER share access to this file!

5. Edit the STATIC_VARS in [collect_eigrp.py](./collect_eigrp.py#227-232) lines 227-232 to your values.

6. Run the python script

    ```
    python collect_eigrp.py
    ```

7. Pray it works!
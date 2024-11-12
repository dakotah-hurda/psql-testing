# PostgreSQL Network Tools

# Table of Contents 
- [PostgreSQL Network Tools](#postgresql-network-tools)
- [Table of Contents](#table-of-contents)
- [Overview](#overview)
- [Usage](#usage)
  - [Notes](#notes)
  - [Setup](#setup)

# Overview
This repo is dedicated to housing some utilities I've built to explore intersections between Python-based network automation and PostgreSQL database interactions.

> :warning: Use these scripts at your own risk. These have not been thoroughly tested against any specific hardware/software releases. See [LICENSE](./LICENSE) for details.

> :warning: Always test code in a safe test environment before using in production environments!

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

4. Add all relevant variables to [the .env file.](https://github.com/dakotah-hurda/psql-testing/blob/main/.env)

5. 
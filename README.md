# How to run 

## Env setup

Have a .env file with your twitter username and password. The script will use this to log in.

```
TWITTER_USERNAME=your_username
TWITTER_PASSWORD=your_password
```

## Running

The script are made to run using uv. 

If you dont have uv installed, you can do 

```
pip install uv
```

Then to run:

```
uv run 04_twitter_bookmarks_advanced.py

# or 

uv run 06_twitter_likes_scraper.py 
```

Once this is done, then all of your bookmarks and likes will be in a sqlite DB in the output_data folder. 

The tool will download entire threads for you, and also get the parent tweets for any replies as well.

import feedparser
feed = feedparser.parse("https://feedparser.readthedocs.io/en/latest/examples/rss20.xml")

# title 
print("Feed Title:", feed.feed.title)
# link
print("Feed Link:", feed.feed.link)
# description
print("Feed Description:", feed.feed.description)
# publication date
print("Feed Published Date:", feed.feed.published)
# publication date (parsed)
print("Feed Published Date (Parsed):", feed.feed.published_parsed)
# entries
print("Number of Entries:", len(feed.entries))
# first entry title
print("First Entry Title:", feed.entries[0].title) # same for link, description, published, published_parsed
# first entry id
print("First Entry ID:", feed.entries[0].id)
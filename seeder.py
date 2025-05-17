import csv
from pymongo import MongoClient
from bson import ObjectId
import json
import ssl
import certifi

# Connect to MongoDB
client = MongoClient(
    "XXXXXXXXXXXXXXXXXXXXXXXXX",
    tls=True,
    tlsCAFile=certifi.where()
)
db = client["test"]
collection = db["ride_locations"]

# Find documents where parent matches a specific ObjectId
parentId = "XXXXXXXXXXX"

parent = collection.find_one({"_id": ObjectId(parentId)})
docx = collection.find({"parent": parentId})

landmarks = [
  "hospital",
  "clinic",
  "police station",
  "fire station",
  "post office",
  "airport",
  "bus station",
  "train station",
  "university",
  "school",
  "college",
  "hotel",
  "shopping mall",
  "supermarket",
  "bank",
  "atm",
  "restaurant",
  "cafe",
  "theater",
  "cinema",
  "park",
  "mosque",
  "playground",
  "pharmacy",
  "courthouse",
  "museum",
  "library",
  "stadium"
]

# Open a CSV file for writing
with open('locations.csv', mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    for doc in docx:
        name = doc.get('name')
        if name:
            for landmark in landmarks:
                writer.writerow([landmark + ' near ' + name +' - '+ parent.get('name'), parent.get('_id')])

import json
import csv
from bs4 import BeautifulSoup
import requests
import time

def scrape_page(page_number, writer):
    print(f"Scraping page {page_number}...")
    url = f"https://om.opensooq.com/en/cars/cars-for-sale?search=true&page={page_number}"
    print(f"Fetching URL: {url}")

    try:
        page_to_scrape = requests.get(url)
        soup = BeautifulSoup(page_to_scrape.text, "html.parser")
        print(soup)
        #Extract car listings
        cars = soup.find_all("script", type="application/ld+json")
        if not cars:
            print(f"No car listings found on page {page_number}.")
            return False  #No more pages

        for car in cars:
            try:
                #Load JSON content
                car_json = json.loads(car.string)
                #Check if it's a car listing
                if car_json.get("@type") == "ItemList":
                    #Iterate through car items
                    for item in car_json['itemListElement']:
                        name = item['name']
                        price = item['offers']['price']
                        currency = item['offers']['priceCurrency']
                        url = item['url']
                        image = item['image']

                        #Print debugging info
                        print(f"Fetching details for: {url}")

                        # Fetch detailed car page
                        specCar = requests.get(url)
                        soup2 = BeautifulSoup(specCar.text, "html.parser")

                        #Extract details from the section with specific id
                        section = soup2.find("section", {"id": "PostViewInformation"})
                        if section:
                            details = {}
                            for li in section.find_all("li"):
                                label_tag = li.find("p")
                                value_tag = li.find("a")
                                label = label_tag.get_text(strip=True) if label_tag else "Unknown"
                                value = value_tag.get_text(strip=True) if value_tag else "Not available"
                                details[label] = value

                            #Add new fields dynamically if not in fieldnames
                            for key in details.keys():
                                if key not in writer.fieldnames:
                                    writer.fieldnames.append(key)
                                    writer.writeheader()  #Re-write header with new/updated fieldnames

                            #Prepare row data
                            row = {
                                'Name': name,
                                'Price': f"{price} {currency}",
                                'URL': url,
                                'Image': image,
                                **details
                            }

                            #Write to CSV
                            writer.writerow(row)

                            #Print extracted details
                            print(f"Car: {name}\nPrice: {price} {currency}\nURL: {url}\nImage: {image}")
                            for key, value in details.items():
                                print(f"{key}: {value}")
                            print("\n")
                        else:
                            print("No detailed information section found.")

            except Exception as e:
                print("Error processing car listing:", e)

        return True  #There might be more pages

    except Exception as e:
        print("Error fetching page:", e)
        return False  # Stop on error

def main():
    #Initialize the fieldnames with  fields
    fieldnames = ['Name', 'Price', 'URL', 'Image', 'Condition', 'Car Make', 'Model', 'Trim', 'Year', 'Kilometers',
                  'Body Type', 'Number of Seats', 'Fuel', 'Transmission', 'Engine Size (cc)', 'Exterior Color',
                  'Interior Color', 'Regional Specs', 'Car License', 'Insurance', 'Body Condition', 'Paint',
                  'Payment Method', 'City', 'Neighborhood', 'Category', 'Subcategory', 'Interior Options',
                  'Exterior Options', 'Technology Options', 'VIN Number']

    #Open CSV file for writing
    with open("car_listings.csv", mode="w", newline='', encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        page_number = 1
        while True:
            has_more_pages = scrape_page(page_number, writer)
            if not has_more_pages:
                break
            page_number += 1
            time.sleep(2)  #Delay between requests to avoid being blocked

if __name__ == "__main__":
    main()

from mcp.server import MCPServer    
import sys
import requests
import re
from bs4 import BeautifulSoup
import cloudscraper
from langchain_text_splitters import RecursiveCharacterTextSplitter
from opencage.geocoder import OpenCageGeocode
from duckduckgo_search import DDGS

try:
    from models import (
        SocialLinksResponse,
        ScrapedContentResponse,
        ContactInfoResponse,
        DistanceResponse,
    )
except ImportError:
    from server.models import (
        SocialLinksResponse,
        ScrapedContentResponse,
        ContactInfoResponse,
        DistanceResponse,
    )

mcp = MCPServer("resource-finder-agent")



try:
    @mcp.tool(name="search_social_links", description="Searches for links using DuckDuckGo")
    def search_social_links(query: str, max_results: int = 10) -> SocialLinksResponse:
        """Searches for links using DuckDuckGo.
        Args:
            query: The search query for social services.
            max_results: Maximum number of links to retrieve.
        Returns:
            SocialLinksResponse: Contains list of social service organization links.
        """
        query_text = query.query if hasattr(query, "query") else str(query)
        links = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query_text, max_results=max_results))
                for result in results:
                    link = result.get("href") or result.get("link", "")
                    if link:
                        links.append(link)
        except Exception as e:
            print(f"DuckDuckGo search error: {e}", file=sys.stderr)

        return SocialLinksResponse(links=links)
except Exception as e:
    print(f"Tool registration failed: {e}", file=sys.stderr)


try:
    @mcp.tool(name="social_org_scraper", description="Scrapes content from a given website URL using cloudscraper to bypass bot protections")
    def social_org_scraper(request: str) -> ScrapedContentResponse:
        """
        Scrapes content from a given website URL using cloudscraper to bypass bot protections.
        Args:
            request: Contains the URL to scrape.
        Returns:
            ScrapedContentResponse: Contains the scraped page content in chunks.
        """
        # Create SSL context separately
        ssl_context = ssl.create_default_context()
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.set_ciphers('HIGH:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!SRP')
        
        # Create scraper with the SSL context
        scraper = cloudscraper.create_scraper(
            ssl_context=ssl_context
        )

        response = scraper.get(str(request.url), timeout=10)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style tags, to ensure we only get the visible text content
            for script_or_style in soup(['script', 'style', 'noscript', 'meta', 'link']):
                script_or_style.decompose()
            
            # Get raw text with proper spacing
            raw_text = soup.get_text(separator='\n', strip=True).lower()
            
            # Clean up multiple spaces and newlines
            raw_text = re.sub(r'\s+', ' ', raw_text).strip()
            
            # SPLIT TEXT INTO CHUNKS:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=350,  
                chunk_overlap=70,
                separators=["\n\n", "\n", " ", ""]
            )
            chunks = text_splitter.split_text(raw_text)
            
            return ScrapedContentResponse(chunks=chunks)
        else:
            print(f"Failed to fetch URL. Status code: {response.status_code}")
            return ScrapedContentResponse(chunks=[])

except Exception as e:
    print(f"Tool registration failed: {e}", file=sys.stderr)
       
       
try:
    @mcp.tool(name="extract_us_addresses_and_phone_numbers", description="Extracts US phone numbers and addresses from text chunks")   
    def extract_us_addresses_and_phone_numbers(input: str) -> ContactInfoResponse:
        """Extracts US phone numbers and addresses from the given list of strings.
        Args:
            input: Contains the text chunks to analyze.
        Returns:
            ContactInfoResponse: Contains phone numbers and addresses found.
        """
        result = {
            "phone_numbers": [],
            "addresses": []
        }

        seen_numbers = set()
        seen_addresses = set()

        for text in input.website_chunks:
            # --- Extract Phone Numbers ---
            for match in PhoneNumberMatcher(text, "US"):
                if phonenumbers.is_valid_number(match.number):
                    formatted = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
                    if formatted not in seen_numbers:
                        result["phone_numbers"].append(formatted)
                        seen_numbers.add(formatted)

            # --- Extract Addresses ---
            possible_lines = re.split(r'[.\n]', text)
            for line in possible_lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    tagged_address, _ = usaddress.tag(line)
                    if 'AddressNumber' in tagged_address and 'StreetName' in tagged_address:
                        if line not in seen_addresses:
                            result["addresses"].append(line)
                            seen_addresses.add(line)
                except usaddress.RepeatedLabelError:
                    continue

        return ContactInfoResponse(**result)
except Exception as e:
    print(f"Tool registration failed: {e}", file=sys.stderr)   


try:
    @mcp.tool(name="distance_calculator", description="Calculate distance between two addresses. Format: 'addr1 || addr2'")
    def distance_calculator(input: str) -> DistanceResponse:
        """Calculate distance between two addresses. Format: 'addr1 || addr2'.
        
        Args:
            input: Contains the address pair to calculate distance between.
            
        Returns:    
            DistanceResponse: Contains the distance result or error message.
        """
        from_address, to_address = [a.strip() for a in input.address_pair.split("||")]
        
        geocoder = OpenCageGeocode(OPENCAGE_API_KEY)

        # Geocode from address
        from_coords = None
        try:
            result_from = geocoder.geocode(from_address)
            if result_from:
                from_coords = (result_from[0]['geometry']['lat'], result_from[0]['geometry']['lng'])
        except Exception as e:
            print(f"Geocoding failed for '{from_address}': {e}")
            return DistanceResponse(distance=f"❌ Could not geocode: {from_address}")

        # Geocode to address
        to_coords = None
        try:
            result_to = geocoder.geocode(to_address)
            if result_to:
                to_coords = (result_to[0]['geometry']['lat'], result_to[0]['geometry']['lng'])
        except Exception as e:
            print(f"Geocoding failed for '{to_address}': {e}")
            return DistanceResponse(distance=f"❌ Could not geocode: {to_address}")

        # Calculate driving distance using OSRM
        if from_coords and to_coords:
            try:
                url = f"http://router.project-osrm.org/route/v1/driving/{from_coords[1]},{from_coords[0]};{to_coords[1]},{to_coords[0]}"
                response = requests.get(url, params={'overview': 'false'}, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get("routes"):
                    distance_miles = data["routes"][0]["distance"] / 1609.34
                    return DistanceResponse(distance=f"Distance from {from_address} to {to_address} is {round(distance_miles, 2)} miles.")
                else:
                    return DistanceResponse(distance=f"❌ Could not calculate distance from {from_address} to {to_address}.")
            except Exception as e:
                print(f"Distance error: {e}")
                return DistanceResponse(distance=f"❌ Error calculating distance from {from_address} to {to_address}.")
        else:
            return DistanceResponse(distance=f"❌ Could not geocode one or both addresses: '{from_address}' → '{to_address}'")
except Exception as e:
    print(f"Tool registration failed: {e}", file=sys.stderr)
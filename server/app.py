import logging
import tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(level)s - %(message)s"
)


logger = logging.getLogger("resource finder logger")


def main():
    """
    Main entry point for the resource-finder-agent server"
    """

    server = MCPServer("resource-finder-agent")

    server.add_tool(tools.distance_calculator)
    server.add_tool(tools.extract_us_addresses_and_phone_numbers)
    server.add_tool(tools.search_social_links)
    server.add_tool(tools.social_org_scraper)

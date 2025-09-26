from typing import Annotated, Literal  

from pydantic import Field  


URL = Annotated[
    str, Field(description="The URL of the website to be scraped.")
]
RENDER = Annotated[  
    str, 
    Field( 
        description="Proxy configuration selector (Unlocker for unlocker, other values for regular proxy)", 
    ),
]

OUTPUT_FORMAT = Annotated[  # Define an Annotated type named OUTPUT_FORMAT
    Literal[  # Its base type is Literal
        "",  # Allow empty string
        "links",  # Allow "links"
        "Markdown",  # Allow "Markdown"
        "html",  # Allow "html"
    ],
    Field(  # And add a Field
        description=""" # Describes the output format.
        Output format:
            - links - When you need links or navigation from the page.
            - Markdown - When you need the page in readable MarkDown format.
            - html - When you need the page in pure HTML format.
        """
    ),
]

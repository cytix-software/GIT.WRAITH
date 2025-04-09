flowchart TD
    %% Styles
    classDef user fill:#fdd,stroke:#333,stroke-width:2px
    classDef process fill:#ddf,stroke:#333,stroke-width:2px
    classDef storage fill:#dfd,stroke:#333,stroke-width:2px
    classDef control fill:#fff,stroke:#f66,stroke-width:3px
    classDef external fill:#fdb,stroke:#333,stroke-width:2px
    
    %% Trust Boundaries
    subgraph ClientZone[Wraith Frontend]
        User((User))
        Frontend[script.js]
    end
    
    subgraph ServerZone[Wraith Server]
        API[api.py]
        Server[serveStatic.py]
        Bottle{{Bottle_Framework}}
    end
    
    subgraph DataZone[GitHub]
        GitHub((GitHub))
        Repo[(GitHub_Repository)]
    end
    
    %% Data Flows
    User -->|github_repo_url| Frontend
    Frontend -->|github_repo_url| API
    API -->|clone_repo_request| GitHub
    GitHub -->|repo_files_data| API
    API -->|processed_repo_data| Frontend
    Frontend -->|static_file_request| Server
    Server -->|static_file_response| Frontend
    
    %% Apply styles
    class User user
    class GitHub external
    class API process
    class Repo storage
    class Frontend process
    class Server process
    class Bottle control
Install dependencies:

```shell
make install
```

Run checks:

```shell
make check
```

Run format:

```shell
make format
```

Automatically fix issues (format, lint):

```shell
make fix
```

Run docs:

```shell
make docs/serve
```

By default, the Engine looks for the nodes library in the location we install to:
https://github.com/griptape-ai/griptape-nodes/blob/24d1fdab898e1617793eeb55b7a5a87c161502ef/install.sh?plain=1#L63-L64
https://github.com/griptape-ai/griptape-nodes/blob/24d1fdab898e1617793eeb55b7a5a87c161502ef/src/griptape_nodes/retained_mode/managers/settings.py?plain=1#L52-L54

When developing locally, we want to configure the Engine to use the nodes library in this repo:

1. Create a file `griptape_nodes_config.json` in the root of your project.
1. Add the following content to the file:
   ```json
   {
     "app_events": {
       "on_app_initialization_complete": {
         "libraries_to_register": [
           "nodes/griptape_nodes_library.json"
         ]
       }
     }
   }
   ```

Review [Makefile](https://github.com/griptape-ai/griptape-nodes/blob/main/Makefile) for more commands.

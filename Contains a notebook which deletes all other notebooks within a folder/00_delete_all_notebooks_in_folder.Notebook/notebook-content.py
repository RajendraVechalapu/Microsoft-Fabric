# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

# Deletes every notebook in THIS notebook's folder (except this one).
# Step 1: run with DRY_RUN = True to preview. Step 2: set DRY_RUN = False and run again.
DRY_RUN = True

import sempy.fabric as fabric
import notebookutils

ws = fabric.get_workspace_id()
me = notebookutils.runtime.context["currentNotebookId"]
client = fabric.FabricRestClient()
my_folder = client.get(f"v1/workspaces/{ws}/items/{me}").json().get("folderId")
items = client.get(f"v1/workspaces/{ws}/items?type=Notebook").json().get("value", [])
targets = sorted([i for i in items if i.get("folderId") == my_folder and i["id"] != me], key=lambda x: x["displayName"])
print(f"{len(targets)} notebooks found in this folder:")
print("\n".join(" - " + i["displayName"] for i in targets))

results = [] if DRY_RUN else [(i["displayName"], client.delete(f"v1/workspaces/{ws}/items/{i['id']}").status_code) for i in targets]
print("\nDRY RUN - nothing deleted. Set DRY_RUN = False and run again." if DRY_RUN else "\n".join(f"{n}: {'Deleted' if s in (200, 204) else 'FAILED ' + str(s)}" for n, s in results))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

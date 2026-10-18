import ElkApi from "elkjs/lib/elk-api.js";
import type { ElkLayoutArguments, ElkNode } from "elkjs/lib/elk-api.js";
import ElkEngineWorker from "elkjs/lib/elk-worker.min.js?worker";
import type { RelationshipEdgeRoute } from "./relationshipRouting";

const engines = new Set<Worker>();
let latestRoutes: RelationshipEdgeRoute[] = [];

export function relationshipRoutes(): RelationshipEdgeRoute[] {
  return latestRoutes;
}

/** Give the plugin an explicit browser worker, without Node/fake-worker probes. */
export default class RelationshipElk {
  private readonly engine: InstanceType<typeof ElkApi>;

  constructor() {
    this.engine = new ElkApi({
      workerFactory: () => {
        const worker = new ElkEngineWorker();
        engines.add(worker);
        worker.onerror = (event) => {
          event.preventDefault();
          throw new Error(event.message);
        };
        worker.onmessageerror = () => {
          throw new Error("relationship_engine_message_failed");
        };
        return worker;
      },
    });
  }

  async layout(graph: ElkNode, args?: ElkLayoutArguments): Promise<ElkNode> {
    // The adapter stores live Cytoscape objects in _cyEle, which cannot cross
    // native worker boundaries. Retain them locally and restore ELK positions
    // onto the original nodes used by the plugin's scratch data.
    const input = JSON.parse(
      JSON.stringify(graph, (key, value: unknown) => (key === "_cyEle" ? undefined : value))
    ) as ElkNode;
    const nodes = new Map(input.children?.map((node) => [node.id, node]) || []);
    for (const node of nodes.values()) {
      node.ports = [];
      node.layoutOptions = { ...node.layoutOptions, "elk.portConstraints": "FIXED_POS" };
    }
    input.edges = input.edges?.map((edge) => {
      const sourceId =
        "source" in edge && typeof edge.source === "string" ? edge.source : edge.sources[0];
      const targetId =
        "target" in edge && typeof edge.target === "string" ? edge.target : edge.targets[0];
      const sourcePort = `${edge.id}-source`;
      const targetPort = `${edge.id}-target`;
      nodes
        .get(sourceId)
        ?.ports?.push({ id: sourcePort, layoutOptions: { "elk.port.side": "SOUTH" } });
      nodes
        .get(targetId)
        ?.ports?.push({ id: targetPort, layoutOptions: { "elk.port.side": "NORTH" } });
      return { id: edge.id, sources: [sourcePort], targets: [targetPort] };
    });
    for (const node of nodes.values()) {
      for (const side of ["NORTH", "SOUTH"]) {
        const ports =
          node.ports?.filter((port) => port.layoutOptions?.["elk.port.side"] === side) || [];
        ports.forEach((port, index) => {
          port.x = 16 + (((node.width || 0) - 32) * (index + 1)) / (ports.length + 1);
          port.y = side === "NORTH" ? 0 : node.height;
          port.width = 0;
          port.height = 0;
        });
      }
    }
    const result = await this.engine.layout(input, args);
    latestRoutes = (result.edges || []).flatMap((edge) => {
      const section = edge.sections?.[0];
      return section
        ? [
            {
              id: edge.id,
              points: [section.startPoint, ...(section.bendPoints || []), section.endPoint],
            },
          ]
        : [];
    });
    const original = new Map<string, ElkNode>();
    const collect = (node: ElkNode) => {
      original.set(node.id, node);
      node.children?.forEach(collect);
    };
    const restore = (node: ElkNode) => {
      const target = original.get(node.id);
      if (target) {
        target.x = node.x;
        target.y = node.y;
        target.width = node.width;
        target.height = node.height;
      }
      node.children?.forEach(restore);
    };
    collect(graph);
    restore(result);
    return graph;
  }
}

export function terminateRelationshipEngines(): void {
  for (const worker of engines) worker.terminate();
  engines.clear();
}

import sys
import logging
import json
import xmlrpc.client
from lamport_mutual_exclusion import LamportMutexSimulatorProcess


def prepare_node_info(node_number: int, total_nodes: int, start_port: int) -> dict:
    info = {
        "self_node_no": node_number,
        "self_port": start_port + node_number,
        "total_nodes": total_nodes,
        "start_port": start_port
    }
    return info

def main():
    # logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    # logger = logging.getLogger("LamportLogger")
    # logger.setLevel(logging.DEBUG)
    logger = logging.getLogger(__name__)
    logging.basicConfig(level = logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] %(process)d |%(levelname)s |%(filename)s:%(lineno)d| %(message)s','%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    no_of_nodes = 4
    start_port = 8000
    simulators = []

    for i in range(no_of_nodes):
        node_info = prepare_node_info(i, no_of_nodes, start_port)
        simulators.append(LamportMutexSimulatorProcess(json.dumps(node_info), logger))
        logger.info(f"Prepared Node {i} on port {node_info['self_port']}")

    for sim in simulators:
        sim.start()

    # Trigger CS operation for each node for demonstration
    for i in range(no_of_nodes):
        host_url = f"http://localhost:{start_port + i}"
        proxy = xmlrpc.client.ServerProxy(host_url)
        try:
            logger.info(f"Triggering CS Operation on Node {i}...")
            result = proxy.trigger_cs_operation()
            logger.info(f"Node {i} operation result: {result}")
        except Exception as e:
            logger.error(f"Error triggering CS operation on Node {i}: {e}")

    for sim in simulators:
        sim.join()

if __name__ == "__main__":
    main()

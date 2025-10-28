import sys
import time
import logging
import threading
import multiprocessing
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
import xmlrpc.client

# ---------------------- RPC Request Handler ----------------------
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)

# ---------------------- Logger Setup ----------------------
def setup_logger(name):
    formatter = logging.Formatter(
        '[%(asctime)s] %(process)d |%(levelname)s |%(filename)s:%(lineno)d| %(message)s',
        '%m-%d %H:%M:%S'
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False
    return logger

# ---------------------- Node Logic ----------------------
class ByzantineNode:
    def __init__(self, node_info, loyal=True, order=None):
        self.node_info = node_info
        self.loyal = loyal
        self.order = order  # only for commander
        self.received_orders = {}  # {sender_id: message}
        self.logger = setup_logger(f"Node{self.node_info['node_id']}")

    def receive_order(self, sender_id, msg):
        self.logger.info(f"Node {self.node_info['node_id']} received order from Node {sender_id}: {msg}")
        self.received_orders[sender_id] = msg
        if sender_id == 0:  # commander also records its own order
            self.received_orders[self.node_info['node_id']] = msg
        return True

    def send_order(self, all_nodes):
        """Commander sends initial order."""
        self.logger.info(f"Commander sending order: {self.order}")
        for n in all_nodes:
            if n == self.node_info["node_id"]:
                continue
            host = f"http://localhost:{self.node_info['start_port'] + n}"
            proxy = xmlrpc.client.ServerProxy(host, allow_none=True)
            send_value = self.order
            # If malicious, flip for certain nodes
            if not self.loyal and n % 2 == 1:
                send_value = "RETREAT" if self.order == "ATTACK" else "ATTACK"
            try:
                self.logger.info(f"Sending {'loyal' if self.loyal else 'traitor'} order '{send_value}' to Node {n}")
                proxy.receive_order(self.node_info["node_id"], send_value)
            except ConnectionRefusedError:
                self.logger.warning(f"⚠️ Could not connect to Node {n} (may have shut down).")

    def round_message(self, all_nodes):
        """Lieutenants forward messages."""
        self.logger.info(f"Lieutenant (Node {self.node_info['node_id']}) forwarding messages...")
        for n in all_nodes:
            if n == self.node_info["node_id"]:
                continue
            if n not in self.received_orders:
                continue
            host = f"http://localhost:{self.node_info['start_port'] + n}"
            proxy = xmlrpc.client.ServerProxy(host, allow_none=True)
            send_value = self.received_orders[self.node_info["node_id"]]
            # Traitor behavior
            if not self.loyal and n % 2 == 0:
                send_value = "RETREAT" if send_value == "ATTACK" else "ATTACK"
            try:
                self.logger.info(
                    f"Node {self.node_info['node_id']} forwarding {'loyal' if self.loyal else 'traitor'} value "
                    f"'{send_value}' to Node {n}"
                )
                proxy.receive_order(self.node_info["node_id"], send_value)
            except ConnectionRefusedError:
                self.logger.warning(f"⚠️ Could not connect to Node {n} (may have shut down).")

    def decide(self):
        """Each node decides based on majority of received orders."""
        self.logger.info("Deciding based on orders received...")
        order_counts = {"ATTACK": 0, "RETREAT": 0}
        for msg in self.received_orders.values():
            order_counts[msg] = order_counts.get(msg, 0) + 1
        result = "ATTACK" if order_counts["ATTACK"] >= order_counts["RETREAT"] else "RETREAT"
        self.logger.info(f"Decision for Node {self.node_info['node_id']}: {result} (orders: {self.received_orders})")
        return result

# ---------------------- Process Function ----------------------
def node_process(node_info, all_nodes, is_commander, loyal, initial_order, ready_event):
    node = ByzantineNode(node_info, loyal=loyal, order=initial_order if is_commander else None)

    server = SimpleXMLRPCServer(("localhost", node_info["self_port"]),
                                requestHandler=RequestHandler,
                                logRequests=False,
                                allow_none=True)
    server.register_introspection_functions()
    server.register_instance(node)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    node.logger.info("XMLRPC server started.")

    # Signal main process that this node is ready
    ready_event.set()
    time.sleep(2)

    # Step 1: Commander sends order
    if is_commander:
        node.logger.info("Commander initiating orders...")
        node.send_order(all_nodes)
    else:
        node.logger.info("Waiting for orders...")
        time.sleep(3)

    # Step 2: Lieutenants forward messages
    if not is_commander:
        time.sleep(2)
        node.round_message(all_nodes)

    # Step 3: Decision phase
    time.sleep(3)
    final_decision = node.decide()
    node.logger.info(f"Node {node_info['node_id']} Final decision: {final_decision}")

    # Wait before shutting down to prevent message loss
    time.sleep(5)
    node.logger.info("Shutting down server gracefully.")
    server.shutdown()

# ---------------------- Main Simulation ----------------------
def main():
    num_nodes = 5  # total nodes
    traitor_nodes = [2]  # list of traitor node IDs
    commander_order = "ATTACK"
    start_port = 8000

    all_nodes = list(range(num_nodes))
    ready_events = [multiprocessing.Event() for _ in range(num_nodes)]

    processes = []
    for i in range(num_nodes):
        info = {
            "node_id": i,
            "self_port": start_port + i,
            "start_port": start_port
        }
        is_commander = (i == 0)
        loyal = (i not in traitor_nodes)
        initial_order = commander_order if is_commander else None

        p = multiprocessing.Process(
            target=node_process,
            args=(info, all_nodes, is_commander, loyal, initial_order, ready_events[i])
        )
        processes.append(p)
        p.start()

    # Wait until all nodes' servers are ready
    for event in ready_events:
        event.wait()

    print("\n✅ All XMLRPC servers are up. Starting simulation...\n")
    time.sleep(2)

    # Wait for all nodes to finish
    for p in processes:
        p.join()

    print("\n🎯 Simulation completed successfully!\n")

if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")  # important for Windows
    main()

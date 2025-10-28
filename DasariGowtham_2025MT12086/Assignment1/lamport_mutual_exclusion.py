import logging
import json
import time
from queue import Queue
from multiprocessing import Process
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer
import xmlrpc.client

# -----------------------------------------------
# Request Handler for XML-RPC
# -----------------------------------------------
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)


# -----------------------------------------------
# Lamport Mutual Exclusion Algorithm Logic
# -----------------------------------------------
class LamportAlgoExecutor:
    def __init__(self, logger: logging.Logger, nodes_info: str):
        self.logger = logger
        self.nodes_info = json.loads(nodes_info)
        self.__timestamp = 0
        self.is_already_in_cs = False
        self.request_queue = Queue(self.nodes_info["total_nodes"])

    def __get_timestamp(self) -> int:
        return self.__timestamp

    def __increment_timestamp(self) -> int:
        self.__timestamp += 1
        self.logger.info(f"[{self.nodes_info['self_node_no']}] Timestamp incremented to {self.__timestamp}")
        return self.__timestamp

    def __add_to_queue(self, site_no: int):
        self.request_queue.put(site_no)
        self.logger.info(f"[{self.nodes_info['self_node_no']}] Added node {site_no} to queue. Current queue: {list(self.request_queue.queue)}")

    def __remove_from_queue(self, site_no: int):
        if site_no in self.request_queue.queue:
            self.request_queue.queue.remove(site_no)
            self.logger.info(f"[{self.nodes_info['self_node_no']}] Removed node {site_no} from queue. Current queue: {list(self.request_queue.queue)}")

    def send_cs_request(self):
        msg = {
            "site_no": self.nodes_info["self_node_no"],
            "timestamp": self.__increment_timestamp()
        }
        responses = {}
        for i in range(self.nodes_info["total_nodes"]):
            if i == self.nodes_info["self_node_no"]:
                continue
            host_url = f"http://localhost:{self.nodes_info['start_port'] + i}"
            proxy = xmlrpc.client.ServerProxy(host_url)
            try:
                self.logger.info(f"[{self.nodes_info['self_node_no']}] Sending CS request to {host_url}: {msg}")
                response = proxy.request_cs_access(json.dumps(msg))
                responses[i] = response
            except Exception as e:
                self.logger.error(f"Error sending CS request to {host_url}: {e}")
        return responses

    def send_release(self):
        for i in range(self.nodes_info["total_nodes"]):
            if i == self.nodes_info["self_node_no"]:
                continue
            host_url = f"http://localhost:{self.nodes_info['start_port'] + i}"
            proxy = xmlrpc.client.ServerProxy(host_url)
            try:
                self.logger.info(f"[{self.nodes_info['self_node_no']}] Sending release notification to {host_url}.")
                proxy.release_notification(self.nodes_info["self_node_no"])
            except Exception as e:
                self.logger.error(f"Error sending release notification to {host_url}: {e}")

    def enter_critical_section(self):
        self.logger.info(f"[{self.nodes_info['self_node_no']}] Attempting to enter CS.")
        self.__add_to_queue(self.nodes_info['self_node_no'])
        responses = self.send_cs_request()
        all_allowed = True
        for i, remote_ts in responses.items():
            self.logger.info(f"[{self.nodes_info['self_node_no']}] Response from Node {i}: {remote_ts}")
            if remote_ts < self.__get_timestamp():
                all_allowed = False
        if all_allowed and self.request_queue.queue[0] == self.nodes_info['self_node_no']:
            self.is_already_in_cs = True
            self.logger.info(f"[{self.nodes_info['self_node_no']}] Entered CS.")
            return True
        self.logger.info(f"[{self.nodes_info['self_node_no']}] CS entry denied/waiting.")
        return False

    def process_received_cs_request(self, msg_str):
        msg = json.loads(msg_str)
        site_no = msg['site_no']
        timestamp = msg['timestamp']
        self.__increment_timestamp()
        self.__add_to_queue(site_no)
        self.logger.info(f"[{self.nodes_info['self_node_no']}] Processed incoming CS request from Node {site_no}, timestamp: {timestamp}")
        return self.__get_timestamp()

    def release_critical_section(self):
        self.is_already_in_cs = False
        self.__remove_from_queue(self.nodes_info['self_node_no'])
        self.logger.info(f"[{self.nodes_info['self_node_no']}] Exited CS, notifying others...")
        self.send_release()

    def process_release_notification(self, site_no):
        self.__remove_from_queue(site_no)
        self.logger.info(f"[{self.nodes_info['self_node_no']}] Received release notification from Node {site_no}")


# -----------------------------------------------
# Process Class for Each Node
# -----------------------------------------------
class LamportMutexSimulatorProcess(Process):
    def __init__(self, node_info_str):
        super().__init__()
        self.nodes_info = json.loads(node_info_str)
        self.executor = None

    def perform_operation(self):
        self.logger.info(f"[{self.nodes_info['self_node_no']}] Performing operation in CS (writing to file...)")
        with open(f"node_{self.nodes_info['self_node_no']}_output.txt", "a") as f:
            f.write(f"CS entered at logical time {self.executor._LamportAlgoExecutor__get_timestamp()}\n")
        time.sleep(2)
        self.logger.info(f"[{self.nodes_info['self_node_no']}] CS operation complete.")

    def trigger_cs_operation(self):
        if self.executor.enter_critical_section():
            self.perform_operation()
            self.executor.release_critical_section()
            return "Operation successful"
        else:
            return "Operation denied/waiting"

    def request_cs_access(self, msg_str):
        self.logger.info(f"[{self.nodes_info['self_node_no']}] Received CS access request: {msg_str}")
        return self.executor.process_received_cs_request(msg_str)

    def release_notification(self, site_no):
        self.executor.process_release_notification(site_no)
        return True

    def run(self):
        # Initialize logger INSIDE each process (important for Windows)
        import sys
        self.logger = logging.getLogger(f"Node-{self.nodes_info['self_node_no']}")
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('[%(asctime)s] %(process)d |%(levelname)s| %(message)s', '%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.propagate = False

        # Initialize Lamport executor
        self.executor = LamportAlgoExecutor(self.logger, json.dumps(self.nodes_info))

        # Start XML-RPC Server
        with SimpleXMLRPCServer(("localhost", self.nodes_info["self_port"]),
                                requestHandler=RequestHandler,
                                allow_none=True, logRequests=False) as server:
            server.register_introspection_functions()
            server.register_function(self.trigger_cs_operation, "trigger_cs_operation")
            server.register_function(self.request_cs_access, "request_cs_access")
            server.register_function(self.release_notification, "release_notification")

            self.logger.info(f"XMLRPC Server running for Node {self.nodes_info['self_node_no']} on port {self.nodes_info['self_port']}")
            server.serve_forever()

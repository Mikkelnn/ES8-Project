import json


def generate_nodes(n):
    nodes = {}

    for i in range(1, n + 1):
        neighbours = []

        if i > 1:
            neighbours.append(i - 1)

        if i < n:
            neighbours.append(i + 1)

        nodes[str(i)] = {
            "point": [float(i), 0.0],
            "neighbours": neighbours
        }

    return {"nodes": nodes}


def write_nodes_to_file_json(n, filename="nodes.json"):
    data = generate_nodes(n)

    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {n} nodes to {filename}")

def write_nodes_to_file_txt(n, filename="nodes.txt"):
    with open(filename, "w") as f:
        f.write('  "nodes": {\n')

        for i in range(1, n + 1):

            neighbours = []

            if i > 1:
                neighbours.append(str(i - 1))

            if i < n:
                neighbours.append(str(i + 1))

            neighbours_str = ",".join(neighbours)

            comma = "," if i < n else ""

            line = (
                f'   "{i}":  {{"point": [{i:.3f}, 0.000],'
                f'"neighbours": [{neighbours_str}]}}{comma}\n'
            )

            f.write(line)

        f.write('  }\n')

    print(f"Wrote {n} nodes to {filename}")


if __name__ == "__main__":
    N = 2400  # change this value
    write_nodes_to_file_txt(N)
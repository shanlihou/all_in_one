import sys
import os
import struct
import argparse
from collections import defaultdict

# Recast 常量
DT_VERTS_PER_POLYGON = 6

def parse_recast_tiles(file_path):
    """
    深度解析 Recast 二进制文件，提取顶点和多边形拓扑。
    """
    if not os.path.exists(file_path):
        return None

    tiles = []
    try:
        with open(file_path, 'rb') as f:
            data = f.read()

        magic_bytes = b'\x56\x41\x4E\x44' # 'VAND' (Little Endian for 'DNAV')
        offset = 0
        
        while True:
            found_idx = data.find(magic_bytes, offset)
            if found_idx == -1:
                break
            
            # 1. 解析 dtMeshHeader (大小通常为 84 字节)
            # 结构参考: 9 ints, 6 floats, 3 floats, 3 ints
            header_offset = found_idx
            try:
                header_data = struct.unpack('<9i6f3f3i', data[header_offset : header_offset + 100][:84])
                poly_count = header_data[6]
                vert_count = header_data[7]
                
                # 计算数据位置
                # Header 之后紧跟 Vertices (float * 3 * vert_count)
                # 然后是 Polys (dtPoly 结构)
                verts_start = header_offset + 84
                polys_start = verts_start + (vert_count * 12)
                
                # dtPoly 结构解析:
                # firstLink(4), verts(2*6), neighbors(2*6), flags(2), vertCount(1), areaAndType(1) = 32 bytes
                tile_verts = []
                for i in range(vert_count):
                    v_idx = verts_start + (i * 12)
                    tile_verts.append(struct.unpack('<3f', data[v_idx : v_idx + 12]))
                
                tile_polys = []
                for i in range(poly_count):
                    p_idx = polys_start + (i * 32)
                    p_data = struct.unpack('<I6H6HHBB', data[p_idx : p_idx + 32])
                    
                    # 提取有效的顶点索引和邻接信息
                    v_count = p_data[15] # vertCount
                    poly_v = list(p_data[1:7])[:v_count]
                    poly_n = list(p_data[7:13])[:v_count]
                    
                    tile_polys.append({
                        'id': i,
                        'verts': poly_v,
                        'neighbors': poly_n
                    })
                
                tiles.append({
                    'header_pos': header_offset,
                    'verts': tile_verts,
                    'polys': tile_polys
                })
            except Exception as e:
                pass # 可能是伪造的 magic
                
            offset = found_idx + 4
        return tiles
    except Exception as e:
        print(f"Error parsing file: {e}")
        return None

def analyze_adjacency(tiles):
    """
    分析几何共享边与逻辑邻接表的差异。
    """
    for t_idx, tile in enumerate(tiles):
        print(f"\n[Tile #{t_idx}] (Polys: {len(tile['polys'])}, Verts: {len(tile['verts'])})")
        
        # 建立边索引: edge -> list of poly_ids
        # edge 表示为 (min_v, max_v)
        edge_to_polys = defaultdict(list)
        for poly in tile['polys']:
            v = poly['verts']
            n = len(v)
            for i in range(n):
                v1, v2 = v[i], v[(i + 1) % n]
                edge = tuple(sorted((v1, v2)))
                edge_to_polys[edge].append(poly['id'])

        # 检查每个 Poly 的邻接表
        issues_found = 0
        for poly in tile['polys']:
            v = poly['verts']
            n = len(v)
            for i in range(n):
                v1, v2 = v[i], v[(i + 1) % n]
                edge = tuple(sorted((v1, v2)))
                logical_neighbor = poly['neighbors'][i] # 0 表示无邻接
                
                # 找出几何上共享这条边的其他多边形
                sharers = [p_id for p_id in edge_to_polys[edge] if p_id != poly['id']]
                
                if sharers:
                    # 情况：几何上有共享，但逻辑上没有标记邻接
                    # 注意：Recast 中 neighbor 是 poly_index + 1，或者 0x8000 以上表示外部连接
                    if logical_neighbor == 0:
                        print(f"  ! Lost Adjacency: Poly {poly['id']} edge ({v1}-{v2}) -> Shared with Poly {sharers}, but Neighbor is NONE")
                        issues_found += 1
                else:
                    # 情况：几何上是边界，但逻辑上标记了邻接（较罕见）
                    if logical_neighbor != 0 and logical_neighbor < 0x8000:
                        print(f"  ? Ghost Neighbor: Poly {poly['id']} edge ({v1}-{v2}) -> Boundary edge, but Neighbor says {logical_neighbor-1}")
                        issues_found += 1
        
        if issues_found == 0:
            print("  No adjacency issues detected in this tile.")
        else:
            print(f"  Found {issues_found} issues in this tile.")

def main():
    parser = argparse.ArgumentParser(description="Recast NavMesh Adjacency Checker")
    parser.add_argument("input", help="Path to the NavMesh .bin/.navmesh file")
    args = parser.parse_args()

    print(f"Loading and Analyzing: {args.input}")
    tiles = parse_recast_tiles(args.input)
    
    if not tiles:
        print("No Recast NavMesh tiles found.")
        return

    analyze_adjacency(tiles)

if __name__ == "__main__":
    main()

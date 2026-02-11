from .full_te import compute_full_te

def get_score(profil_id: str, verbose: bool = True):
    result = compute_full_te(profil_id, save_to_db=False)
    
    if "error" in result:
        print(result["error"])
        return None
    
    if verbose:
        print(f"\nScore pour {profil_id} ({result['csp']}):")
        print(f"  Full TE: {result['full_te']}% → {result['classification']}")
        print(f"  Resources: {result['resources_score']}%")
        print(f"  Market: {result['market_score']}%")
    
    return result

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        get_score(sys.argv[1])
    else:
        print("Usage: python single_score.py DEM-XXXXXXX")
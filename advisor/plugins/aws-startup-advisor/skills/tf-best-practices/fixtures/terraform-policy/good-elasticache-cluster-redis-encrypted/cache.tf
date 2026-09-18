# Compliant fixture — MUST pass (POLICY_OK).
# A single-node Redis aws_elasticache_cluster with both encryption flags on.
resource "aws_elasticache_cluster" "good" {
  cluster_id                 = "good-redis-cluster"
  engine                     = "redis"
  node_type                  = "cache.t4g.micro"
  num_cache_nodes            = 1
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}

module "bucket" {
  source      = "./bucket"
  name_prefix = "semantic-search-bucket"
}

module "policy" {
  source         = "./policy"
  s3_bucket_name = module.bucket.name
  s3_bucket_arn  = module.bucket.arn

  depends_on = [module.bucket]
}
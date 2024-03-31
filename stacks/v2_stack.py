import aws_cdk as cdk
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_s3_deployment as s3deploy
import aws_cdk.aws_iam as iam
import aws_cdk.aws_glue as glue
import aws_cdk.aws_lambda as lambda_

class FinalCloudProjectV2Stack(cdk.Stack):
    def __init__(self, scope: cdk.App, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Glue IAM role for accessing data bucket
        glue_role = iam.Role(self, "my_glue_role",
                        assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
                        managed_policies=[
                        iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")])
        
    
        # Create Secrets manager access policy to the above role
        # For retrieving Ticketmaster API key
        secrets_manager_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["secretsmanager:GetSecretValue"],
            resources=["arn:aws:secretsmanager:us-west-2:943686807189:secret:finalproject/daniel/ticketmaster-Gu2UO4"]
        )

        # Attach policy to the role
        glue_role.add_to_policy(secrets_manager_policy)

        # Create bucket for data storage
        data_bucket = s3.Bucket(self, "final_data",
                                versioned=True,
                                public_read_access=True,
                                removal_policy=cdk.RemovalPolicy.DESTROY,
                                auto_delete_objects=True)

        # Create bucket for housing scripts inside assets
        scripts_bucket = s3.Bucket(self, "glue_scripts",
                                   versioned=True,
                                   block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                                   removal_policy=cdk.RemovalPolicy.DESTROY,
                                   auto_delete_objects=True)

        # Attach Glue IAM role to each of the buckets
        data_bucket.grant_read_write(glue_role)
        scripts_bucket.grant_read(glue_role)

        # Dump assets scripts into glue script bucket
        s3deploy.BucketDeployment(self, "deploy_assets",
                                  sources=[s3deploy.Source.asset("./assets/")],
                                  destination_bucket=scripts_bucket,
                                  destination_key_prefix="assets/")
        
        # Initialize glue workflow
        my_workflow = glue.CfnWorkflow(self, "ticketmaster_workflow",
                                description="Workflow for processing Ticketmaster data to parquet")

        # Job to download data from ticketmaster, convert to parquet,
        # and dump into the data bucket
        ticketmaster_download_job = glue.CfnJob(self, "download_ticketmaster_data",
                                                name="download_ticketmaster_data",
                                                command=glue.CfnJob.JobCommandProperty(
                                                    name="pythonshell",
                                                    python_version="3.9",
                                                    script_location=f"s3://{scripts_bucket.bucket_name}/assets/ticketmaster_to_parquet.py"
                                        ),
                                        role=glue_role.role_arn,
                                        glue_version="3.0",
                                        max_capacity=1,
                                        timeout=3,
                                        default_arguments={
                                            "--my_bucket": data_bucket.bucket_name
                                        })

        # Second job that takes the data out of new pull, processes it
        # and converts into a single large parquet inside combined_data.parquet
        fragments_to_parquet_job = glue.CfnJob(self, "fragments_to_parquet_job",
                                               name="fragments_to_parquet_job",
                                               command=glue.CfnJob.JobCommandProperty(
                                                    name="pythonshell",
                                                    python_version="3.9",
                                                    script_location=f"s3://{scripts_bucket.bucket_name}/assets/merge_parquet_final.py"
                                        ),
                                        role=glue_role.role_arn,
                                        glue_version="3.0",
                                        max_capacity=1,
                                        timeout=3,
                                        default_arguments={
                                            "--my_bucket": data_bucket.bucket_name
                                        })
        
        # Third job that takes combined data
        parquet_analysis_job = glue.CfnJob(self, "parquet_analysis_job",
                                           name="parquet_analysis_job",
                                           command=glue.CfnJob.JobCommandProperty(
                                               name="pythonshell",
                                               python_version="3.9",
                                               script_location=f"s3://{scripts_bucket.bucket_name}/assets/V2TicketMasterAnalysis_Final.py"
                                        ),
                                        role=glue_role.role_arn,
                                        glue_version="3.0",
                                        max_capacity=1,
                                        timeout=3,
                                        default_arguments={
                                            "--my_bucket": data_bucket.bucket_name,
                                            "--additional-python-modules": "dython==0.7.5,matplotlib==3.8.3,folium==0.16.0"
                                        })

        # Set up trigger for first job to run daily at 4:00am Cali time
        job_1_trigger = glue.CfnTrigger(self, "initial_trigger",
                                        name="initial_trigger",
                                        actions=[glue.CfnTrigger.ActionProperty(job_name=ticketmaster_download_job.name)],
                                        type="SCHEDULED",
                                        start_on_creation=True,
                                        schedule="cron(0 11 * * ? *)",
                                        workflow_name=my_workflow.name)
        

        # Set up trigger for second job to run after first job completes
        job_2_trigger = glue.CfnTrigger(self, "frag_trigger",
                                        name="frag_trigger",
                                        actions=[glue.CfnTrigger.ActionProperty(job_name=fragments_to_parquet_job.name)],
                                        type="CONDITIONAL",
                                        start_on_creation=True,
                                        workflow_name=my_workflow.name,
                                        predicate=glue.CfnTrigger.PredicateProperty(
                                                        conditions=[glue.CfnTrigger.ConditionProperty(
                                                            state="SUCCEEDED",
                                                            logical_operator="EQUALS",
                                                            job_name=ticketmaster_download_job.name
                                                        )]))
        
        # Set up third job trigger to run when second job completes
        job_3_trigger = glue.CfnTrigger(self, "analysis_trigger",
                                        name="analysis_trigger",
                                        actions=[glue.CfnTrigger.ActionProperty(job_name=parquet_analysis_job.name)],
                                        type="CONDITIONAL",
                                        start_on_creation=True,
                                        workflow_name=my_workflow.name,
                                        predicate=glue.CfnTrigger.PredicateProperty(
                                                        conditions=[glue.CfnTrigger.ConditionProperty(
                                                            state="SUCCEEDED",
                                                            logical_operator="EQUALS",
                                                            job_name=fragments_to_parquet_job.name
                                                        )])
                                        )

        # We ended up not using a glue crawler or catalog, but the code below
        # would be used if this was necessary if Athena needed to be used as the size of the data 
        # continues to grow.

        # Configure data catalog for creating schema on final created parquet in /Processed
        # glue_data_cataloging = glue.CfnDatabase(self, "ticketmaster_db",
        #                                         catalog_id=cdk.Aws.ACCOUNT_ID,
        #                                         database_input=glue.CfnDatabase.DatabaseInputProperty(
        #                                             name="ticketmaster_db",
        #                                             description="Data catalog for ticketmaster data"
        #                                         ))

        # Configure crawler to automatically go through final dataset
        # glue_crawler = glue.CfnCrawler(self, "ticketmaster_crawler",
        #                         name="ticketmaster_crawler",
        #                         role=glue_role.role_arn,
        #                         database_name="ticketmaster_db",
        #                         targets={"s3Targets": [{"path": f"s3://{data_bucket.bucket_name}/Processed"}]})

        # Set up predicate property for next trigger
        # crawler_predicate = glue.CfnTrigger.PredicateProperty(
        #     conditions=[glue.CfnTrigger.ConditionProperty(
        #         job_name=fragments_to_parquet_job.name,
        #         logical_operator="EQUALS",
        #         state="SUCCEEDED"
        #     )]
        # )

        # Trigger the crawler to start when second job succeeds
        # crawler_trigger = glue.CfnTrigger(self, "crawler_trigger",
        #                                 name="crawler_trigger",
        #                                 actions=[glue.CfnTrigger.ActionProperty(crawler_name=glue_crawler.name)],
        #                                 type="CONDITIONAL",
        #                                 predicate=crawler_predicate,
        #                                 workflow_name=my_workflow.name)
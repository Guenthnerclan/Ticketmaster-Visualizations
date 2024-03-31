import aws_cdk as core
import aws_cdk.assertions as assertions

from final_cloud_project_v2.final_cloud_project_v2_stack import FinalCloudProjectV2Stack

# example tests. To run these tests, uncomment this file along with the example
# resource in final_cloud_project_v2/final_cloud_project_v2_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = FinalCloudProjectV2Stack(app, "final-cloud-project-v2")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })

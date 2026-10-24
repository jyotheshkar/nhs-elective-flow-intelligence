"""Planning estimate, not a quotation. Run without AWS credentials."""
from __future__ import annotations
import json
from pathlib import Path

# App Runner Ireland published rate is used as a comparison baseline. For the
# London deployment replace region-dependent assumptions with calculator rates.
INPUTS = {
    'comparison_region':'eu-west-1', 'deployment_region':'eu-west-2',
    'month_hours':730, 'api_vcpu':1, 'api_gb':2, 'active_hours':30,
    'api_gb_hour_published_ireland':0.007, 'api_vcpu_hour_published_ireland':0.064,
    'batch_runs':5, 'batch_minutes_per_run':20, 'batch_vcpu':1, 'batch_gb':4,
    'batch_vcpu_hour_PLANNING_ASSUMPTION':0.06,
    'batch_gb_hour_PLANNING_ASSUMPTION':0.007,
    's3_gb':10, 's3_gb_month_PLANNING_ASSUMPTION':0.03,
    'ecr_gb':2, 'ecr_gb_month_published_example':0.10,
    'public_ipv4_hour_published':0.005,
    'logs_metrics_alarms_notifications_month_PLANNING_ALLOWANCE':3.0,
    'requests_and_egress_month_PLANNING_ALLOWANCE':1.0,
}

def estimate(inputs):
    batch_hours=inputs['batch_runs']*inputs['batch_minutes_per_run']/60
    rows={
        'API provisioned memory':inputs['month_hours']*inputs['api_gb']*inputs['api_gb_hour_published_ireland'],
        'API active CPU':inputs['active_hours']*inputs['api_vcpu']*inputs['api_vcpu_hour_published_ireland'],
        'Batch CPU and RAM':batch_hours*(inputs['batch_vcpu']*inputs['batch_vcpu_hour_PLANNING_ASSUMPTION']+inputs['batch_gb']*inputs['batch_gb_hour_PLANNING_ASSUMPTION']),
        'Batch public IPv4':batch_hours*inputs['public_ipv4_hour_published'],
        'S3 stored bytes':inputs['s3_gb']*inputs['s3_gb_month_PLANNING_ASSUMPTION'],
        'ECR images':inputs['ecr_gb']*inputs['ecr_gb_month_published_example'],
        'Monitoring and notifications allowance':inputs['logs_metrics_alarms_notifications_month_PLANNING_ALLOWANCE'],
        'Requests and egress allowance':inputs['requests_and_egress_month_PLANNING_ALLOWANCE'],
    }
    return {'USD_per_month':{key:round(value,4) for key,value in rows.items()},
            'total_USD_before_tax':round(sum(rows.values()),2)}

if __name__=='__main__':
    output={'status':'ILLUSTRATIVE_PLANNING_ESTIMATE_NOT_A_QUOTE','inputs':INPUTS,
            'low_traffic_30_active_hours':estimate(INPUTS),
            'continuously_active_sensitivity':estimate(dict(INPUTS,active_hours=730)),
            'excludes':['tax','currency conversion','support','additional deployments','extra storage versions','unexpected traffic beyond allowances'],
            'warning':'London rates not independently captured. Replace pricing inputs in AWS Pricing Calculator before deploying.'}
    print(json.dumps(output,indent=2))

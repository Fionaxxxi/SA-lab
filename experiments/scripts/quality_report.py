"""Create auditable quality CSV, figures and a Markdown report."""
import csv
import hashlib
import html
import json
import math
import os
from pathlib import Path
import tempfile


def cell(value):
    if value is None:
        return 'N/A'
    text = html.escape(str(value),quote=False)
    for char,entity in [('|','&#124;'),('[','&#91;'),(']','&#93;'),('*','&#42;'),('_','&#95;'),(chr(96),'&#96;')]:
        text = text.replace(char,entity)
    return text.replace('\r','').replace('\n','<br>')

def percent(value):
    return 'N/A' if value is None else f'{value:.2%}'

def table(headers, rows):
    return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join(
        '| '+' | '.join(cell(value) for value in row)+' |\n' for row in rows)

def csv_file(path, rows):
    def safe(value):
        if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')):
            return "'"+value
        return value
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]) if rows else ['sample_id','task_id','run_id','device_id','model_version','config_version','mode','input_source','split','source_row','eligible','keypoint_id','expected_covered','actual_covered','agreement','actual_evidence_sentence_id','accepted_evidence_sentence_ids','evidence_correct','observation_index'])
        writer.writeheader()
        writer.writerows({key:safe(value) for key,value in row.items()} for row in rows)

def figures(report, output):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'interview-feedback-mpl'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    rows = [row for row in report['per_sample'] if row['eligible']]
    values = [row['cer'] for row in rows]
    target = report['targets']['cer_max']
    fig,axes = plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
    if values:
        axes[0].bar([row['observation_index'] for row in rows],values,color=['#be5c42' if x>target else '#3574a3' for x in values])
        axes[0].scatter([row['observation_index'] for row in rows],values,color='#173d57',s=12,zorder=3)
        if len(rows)<=30:
            axes[0].set_xticks([row['observation_index'] for row in rows])
        else:
            axes[0].xaxis.set_major_locator(MaxNLocator(integer=True))
        axes[0].axhline(target,color='#a83b32',ls='--',label=f'CER target {target:.0%}')
        axes[0].legend()
        bins = max(1,min(10,math.ceil(math.sqrt(len(values)))))
        upper = max(.05,max(values)*1.05)
        edges = [upper*i/bins for i in range(bins+1)]
        axes[1].hist(values,bins=edges,color='#3574a3',edgecolor='white')
        axes[1].axvline(target,color='#a83b32',ls='--')
    else:
        for axis in axes:
            axis.text(.5,.5,'No eligible observations',ha='center',transform=axis.transAxes)
    axes[0].set(title='Per-observation CER',xlabel='Observation index (see per_sample.csv)',ylabel='CER, not clipped at 1')
    axes[1].yaxis.set_major_locator(MaxNLocator(integer=True))
    axes[1].set(title='CER distribution',xlabel='CER',ylabel='Observation count')
    for axis in axes:
        axis.set_ylim(bottom=0)
        axis.spines[['top','right']].set_visible(False)
    fig.suptitle('Quality diagnostics | '+report['condition']+' | split: '+report['selected_split'])
    fig.savefig(output/'cer_distribution.png',dpi=160)
    plt.close(fig)
    summary = report['summary']
    matrix = [[summary['tn'],summary['fp']],[summary['fn'],summary['tp']]]
    fig,axis = plt.subplots(figsize=(5.1,4.3),constrained_layout=True)
    largest = max(1,max(sum(matrix,[])))
    axis.imshow(matrix,cmap='Blues',vmin=0,vmax=largest)
    for y in range(2):
        for x in range(2):
            label = [['TN','FP'],['FN','TP']][y][x]
            axis.text(x,y,label+'\n'+str(matrix[y][x]),ha='center',va='center',fontsize=15,
                      color='white' if matrix[y][x]>largest/2 else '#172b3a')
    axis.set(xticks=[0,1],xticklabels=['Not covered','Covered'],yticks=[0,1],yticklabels=['Not covered','Covered'],
        xlabel='Returned model prediction',ylabel='Supplied reference label',
        title='Coverage confusion | '+report['condition'])
    fig.suptitle('Missing predictions: '+str(summary['missing_predictions'])+' (outside matrix)',fontsize=10)
    fig.savefig(output/'coverage_confusion.png',dpi=160)
    plt.close(fig)

def markdown(report):
    summary,targets = report['summary'],report['targets']
    labels = {'FIXTURE':'测试夹具数据','UNREVIEWED':'待审核数据','REVIEWED':'已登记审核信息的数据'}
    lines = ['# 质量统计报告（'+labels[report['condition']]+'）','',
        '本报告计算输入记录，不自动代替人工复核、阈值校准或 S0–S3 阶段签收。','',
        '输入文件：'+cell(report['input_file']), '输入 SHA256：'+report['input_sha256'],
        '数据标签：'+report['condition']+'；筛选：'+report['selected_split'],'', '## 数据与分母','']
    lines.append(table(['项目','实际值'],[
        ['原始输入条数',report['input_records']],['去除完全重复记录',report['duplicates_removed']],
        ['筛选后的观测条数',summary['observations']],['参与质量计算',summary['recordings']],
        ['预分类无效输入，单列排除',summary['excluded_invalid_inputs']],['不同样本编号',summary['unique_sample_ids']],
        ['已知不同音频哈希',summary['unique_known_audio_hashes']],['缺音频哈希的有效观测',summary['missing_audio_hashes']],
        ['有效输入分类未知的观测',summary['unknown_effective_input']],['归一化参考字符总数',summary['reference_characters']],
        ['编辑错误总数',summary['edit_errors']],['已标注要点数',summary['labeled_keypoints']],
        ['有返回预测的要点数',summary['compared_keypoints']],['未返回预测的要点数',summary['missing_predictions']],
        ['没有要点标注的有效观测',summary['missing_match_labels']],['已审核的返回证据数',summary['evidence_count']]]))
    lines += ['', '## 整体描述性统计与目标对照','']
    def comparison(value,target,lower=False):
        if value is None:
            return '缺测，不判定'
        if target is None:
            return '未设置目标，不判定'
        return '数值在目标内' if (value<=target if lower else value>=target) else '数值未达到目标'
    lines.append(table(['指标','实际值','目标','数值对照'],[
        ['整体 CER（按参考字数加权）',percent(summary['cer']),percent(targets['cer_max']),comparison(summary['cer'],targets['cer_max'],True)],
        ['逐观测 CER 均值',percent(summary['macro_cer']),'未单设','描述性统计'],
        ['逐观测 CER P50 / P90 / P99',' / '.join(percent(summary[k]) for k in ('cer_p50','cer_p90','cer_p99')),'未单设','描述性统计'],
        ['覆盖标签一致率（有预测）',percent(summary['coverage_accuracy']),percent(targets['coverage_accuracy_min']),comparison(summary['coverage_accuracy'],targets['coverage_accuracy_min'])],
        ['全标注要点正确率（缺测不获分）',percent(summary['coverage_correct_rate_all']),'未单设','与上述分母分开'],
        ['预测可用率',percent(summary['prediction_availability']),'未单设','描述性统计'],
        ['Precision / Recall / F1（有预测）',' / '.join(percent(summary[k]) for k in ('precision','recall','f1')),'未单设','分母为零记 N/A'],
        ['返回证据句命中率',percent(summary['evidence_accuracy']),percent(targets['evidence_accuracy_min']),comparison(summary['evidence_accuracy'],targets['evidence_accuracy_min'])]]))
    lines += ['','TP='+str(summary['tp'])+'，TN='+str(summary['tn'])+'，FP='+str(summary['fp'])+'，FN='+str(summary['fn'])+'。',
        '', '默认 CER 对照值 20% 来自项目目标；标签一致率及证据命中率不擅自设目标。数值对照不等于正式验收通过。',
        '', '## 分组结果','']
    lines.append(table(['运行 / 设备','模型 / 配置','模式 / 来源 / 划分','观测数','CER','覆盖一致率','证据命中率'],[
        [str(g['run_id'])+' / '+str(g['device_id']),str(g['model_version'])+' / '+str(g['config_version']),
         str(g['mode'])+' / '+str(g['input_source'])+' / '+str(g['split']),g['recordings'],percent(g['cer']),
         percent(g['coverage_accuracy']),percent(g['evidence_accuracy'])] for g in report['groups']]))
    lines += ['','## 逐观测结果','']
    lines.append(table(['序号','样本 / 任务','来源行','参考字符','错误数','CER','覆盖一致率','说明'],[
        [i,r['sample_id']+' / '+str(r['task_id']),r['source_row'],r['reference_characters'],r['edit_errors'],
         percent(r['cer']),percent(r['coverage_accuracy']),r['exclusion_reason'] or '参与统计']
         for i,r in enumerate(report['per_sample'],1)]))
    lines += ['','图表：cer_distribution.png（逐观测柱图与分布），coverage_confusion.png（混淆矩阵）。完整逐要点审查见 per_keypoint.csv。',
        '', '## 未达标与偏差排查','']
    bad = [r for r in report['per_sample'] if r['eligible'] and (r['edit_errors'] or r['fp'] or r['fn'] or
        r['missing_predictions'] or r['evidence_count']!=r['evidence_correct'])]
    bad.sort(key=lambda r:(r['cer'],r['fp']+r['fn']+r['missing_predictions'],r['evidence_count']-r['evidence_correct']),reverse=True)
    if not bad:
        lines.append('已提供记录中未发现上述非零错误；缺少的标注或预测仍按分母说明处理，不能推导未测条件无误差。')
    for row in bad[:10]:
        lines += ['', '### '+cell(row['sample_id'])+' / '+cell(row['task_id']),
            '来源行 '+str(row['source_row'])+'；CER '+percent(row['cer'])+'；FP/FN '+str(row['fp'])+'/'+str(row['fn'])+
            '；未返回预测 '+str(row['missing_predictions'])+'；证据未命中 '+str(row['evidence_count']-row['evidence_correct'])+'。',
            '', '参考转写：'+cell(row['reference_text']), '', '实际转写：'+cell(row['actual_text']),
            '', '检查对应音频、片段边界、转写和逐要点审核；本报告不自动把偏差归因于某个算法模块。']
    lines += ['','## 口径与限制','',
        '- CER 为编辑距离总和 / 参考字符总和；逐观测均值另列，不把二者混用。仅去空白和 Unicode 标点，不改大小写和数字。',
        '- 空实际转写计入错误；CER 可以超过 100%，不截断。有效参考转写归一化后为空则拒绝输入。',
        '- 覆盖一致率 = (TP+TN)/(TP+TN+FP+FN)。预测缺测单列；全标注要点正确率把缺测保留在分母且不给正确分。',
        '- 证据命中率只计算返回“已覆盖”的、具备明确审核接受集合的项；分母为零记 N/A，不填成 0 或 100%。',
        '- 预分类无效输入保留在明细但排除质量指标；未分类记录单列，不补造分类。相同任务冲突拒绝，完全重复只计一次。',
        '- 同题不跨校准/评价集；不同运行、设备、模型、配置、模式、来源和划分分别列出。',
        '- CSV 文本以安全文本方式供表格软件读取；原始字节以 review_input.json 保留，哈希可核对。']
    lines += ['- '+note for note in report['notes']]
    return '\n'.join(lines)+'\n'

def write_report(report, output, source_bytes=None):
    if source_bytes is not None and hashlib.sha256(source_bytes).hexdigest()!=report['input_sha256']:
        raise ValueError('Report input hash differs from supplied source bytes')
    output.mkdir(parents=True,exist_ok=False)
    if source_bytes is not None:
        (output/'review_input.json').write_bytes(source_bytes)
    data = {key:value for key,value in report.items() if key not in ('per_sample','per_keypoint')}
    (output/'quality_summary.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    csv_file(output/'per_sample.csv',report['per_sample'])
    csv_file(output/'per_keypoint.csv',report['per_keypoint'])
    csv_file(output/'group_metrics.csv',report['groups'])
    figures(report,output)
    (output/'quality_report.md').write_text(markdown(report),'utf-8')
    hashes = {file.name:hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted(output.iterdir()) if file.is_file()}
    (output/'artifact_sha256.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n','utf-8')

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import subprocess
import urllib
import hashlib
import time
import shutil
import string
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy import create_engine 
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


REMOTE_HTTP_SERVER="http://data.com/package/"
LOCAL_FILE_PATH="/etc/ansible/roles/deploy/files/"

PACKAGE_NAME = {
        "fronted": "frontend.jar",
}



Base = declarative_base()

## 消息入库
class DeployModel(Base):
    __tablename__ = 'deploy'
    id = Column(Integer, primary_key=True, autoincrement=True, unique=True)
    cluster_name = Column(String(255))
    deploy_type = Column(String(255))
    deploy_time = Column(String(255))
    backup_file_path = Column(String(255))
    md5sum = Column(String(255))
    new_md5sum = Column(String(255))
    
engine = create_engine("sqlite:///deploy.db")
Base.metadata.create_all(engine)
db_session = sessionmaker(bind=engine)
session = db_session()


def is_valid_date(str_date):
    '''判断是否是一个有效的日期字符串'''
    try:
        time.strptime(str_date, "%Y%m%d")
        return True
    except Exception:
        raise Exception("时间参数错误 near : {}".format(str_date))
        return False

def urlcallback(downloaded,size,total):  
    prec=100.0*downloaded*size/total  
    if 100 < prec:
        pass

def md5sum(filename):
    m = hashlib.new('md5')
    f = open(filename,'rb')
    m.update(f.read())
    f.close()
    return m.hexdigest()


def download(name):
    app_jar = PACKAGE_NAME[name]
    current_date = time.strftime("%Y%m%d")
    if not os.path.exists(LOCAL_FILE_PATH+current_date):
        os.mkdir(LOCAL_FILE_PATH+current_date)

    file_md5,_ = urllib.urlretrieve("%s%s.md5sum" % (REMOTE_HTTP_SERVER, app_jar), "%s%s.md5sum" % (LOCAL_FILE_PATH,app_jar))
    with open(file_md5, "r") as f:
        check_md5 = f.readlines()[0].split(" ")[0].strip()

    old_md5sum = ''
    back_file_path = ''
    if os.path.exists(LOCAL_FILE_PATH+app_jar):
        local_md5sum = md5sum(LOCAL_FILE_PATH+app_jar) 
        old_md5sum = local_md5sum
        if local_md5sum == check_md5:
            return "md5sum:%s 与之前相同，无需下载" % check_md5
        deploy_num = len([package_name for package_name in os.listdir(LOCAL_FILE_PATH+current_date) if package_name.startswith(app_jar)]) + 1
        shutil.move(LOCAL_FILE_PATH+app_jar, "{local_dir}{backup_date}/{app_jar}.{num}".format(local_dir=LOCAL_FILE_PATH, backup_date=current_date,num=deploy_num, app_jar=app_jar))
        back_file_path =  "{backup_date}/{app_jar}.{num}".format(local_dir=LOCAL_FILE_PATH, backup_date=current_date,num=deploy_num, app_jar=app_jar)

    filename,_ = urllib.urlretrieve("%s%s" % (REMOTE_HTTP_SERVER, app_jar), "%s%s" % (LOCAL_FILE_PATH, app_jar), urlcallback)
    jar_md5 = md5sum(filename)
    if check_md5 != jar_md5:
        os.remove(LOCAL_FILE_PATH+app_jar)
        return "md5sum不正确,可能下载不完整导致或者包名又变更，请检查或者重试"

    deploy_time =  time.strftime("%Y-%m-%d %H:%M:%S",time.localtime()) 
    new_message = DeployModel(cluster_name=name,deploy_type="deploy", deploy_time=deploy_time, backup_file_path=back_file_path, md5sum=old_md5sum, new_md5sum=jar_md5)
    session.add(new_message)
    session.commit()
    return jar_md5

def rollback(name):
    app_jar = PACKAGE_NAME[name]
    data = session.query(DeployModel).filter_by(cluster_name=name).all()
    if data == None or len(data) == 0:
            print("该业务没有备份包")
            sys.exit()
     
    import prettytable as pt
    

    data = data[-10:]

    table = pt.PrettyTable()
    table.field_names = ["序号", "集群名称", "部署类型", "取包时间", "备份路径", "旧包MD5", "新包MD5"]
    for index,i in enumerate(data):
        table.add_row([index, i.cluster_name, i.deploy_type, i.deploy_time, i.backup_file_path, i.md5sum[16:], i.new_md5sum[16:]])
     
    print(table)
    num = raw_input("请输入回滚的版本序号:")
    if num == "q" or num == "quit":
            sys.exit()
    try:
            num = int(num)
    except:
        print("输入不合法，请输入数字且序号范围：0 - %s" % str(len(data)-1))
        sys.exit()

    if num > len(data)-1:
            print("输入数字超过备份列表范围,合法范围为: 0 - %s" % str(len(data)-1))
            sys.exit()
    package = data[int(num)]

    if not os.path.exists(LOCAL_FILE_PATH+package.backup_file_path):
            print("很遗憾，备份文件被丢到到火星或者第一次部署,请检查!")
            sys.exit()
    shutil.copy(LOCAL_FILE_PATH+package.backup_file_path, LOCAL_FILE_PATH+app_jar)

    deploy_time =  time.strftime("%Y-%m-%d %H:%M:%S",time.localtime()) 
    new_message = DeployModel(cluster_name=name,deploy_type="rollback", deploy_time=deploy_time, backup_file_path=" ", md5sum=package.md5sum, new_md5sum="")
    session.add(new_message)
    session.commit()
    print("已取回备份包,可以进行部署了")
    return md5sum(LOCAL_FILE_PATH+app_jar)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print "Usage: %s %s" % (sys.argv[0], "|".join(PACKAGE_NAME.keys()))
        sys.exit()

    if len(sys.argv) == 2:
        for i in sys.argv[1].split(","):
            if i in  PACKAGE_NAME.keys():
                print(download(i))
            else:
                print "没有找到该集群名称: %s" % i
                print "Usage: %s %s" % (sys.argv[0], "|".join(PACKAGE_NAME.keys()))
                continue
        sys.exit
    if len(sys.argv) > 2 and sys.argv[1] in PACKAGE_NAME.keys() and sys.argv[2] == 'rb':
        print(rollback(sys.argv[1])) 